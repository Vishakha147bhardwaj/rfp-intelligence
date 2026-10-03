"""LLM client: Claude with tool-based structured output, validation re-asks, retries, usage logs."""

import time
from typing import Literal, TypeVar

import anthropic
import structlog
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from rfp.settings import Settings, get_settings

log = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)
Tier = Literal["smart", "fast"]
TOOL_NAME = "submit"
SUBMIT_INSTRUCTION = f"\n\nAlways respond by calling the {TOOL_NAME} tool exactly once."

# Worth retrying: the request may succeed if we wait. Auth/validation errors are not.
TRANSIENT_ERRORS = (
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


class LLMError(RuntimeError):
    """An LLM call failed permanently (after retries)."""


class LLMUsage(BaseModel):
    agent: str
    model: str
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: int = 0

    def add(self, u) -> None:
        self.attempts += 1
        self.input_tokens += u.input_tokens
        self.output_tokens += u.output_tokens
        self.cache_read_tokens += getattr(u, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(u, "cache_creation_input_tokens", 0) or 0


def _forced_tool_unsupported(exc: Exception) -> bool:
    return isinstance(exc, anthropic.BadRequestError) and "tool_choice" in str(exc)


class LLMClient:
    def __init__(self, settings: Settings | None = None):
        settings = settings or get_settings()
        if not settings.anthropic_api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set - copy .env.example to .env and add your key"
            )
        self.cfg = settings.llm
        self.models: dict[str, str] = {
            "smart": settings.llm_model_smart,
            "fast": settings.llm_model_fast,
        }
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=self.cfg.timeout_s,
            max_retries=0,  # tenacity owns retries, so attempts aren't multiplied
        )
        self._no_forced_tool: set[str] = set()  # models that reject tool_choice "tool"

    def structured(
        self,
        *,
        agent: str,
        system: str,
        user: str,
        response_model: type[T],
        tier: Tier = "fast",
        max_tokens: int | None = None,
    ) -> tuple[T, LLMUsage]:
        """Ask Claude for a validated `response_model`. Raises LLMError on permanent failure."""
        model = self.models[tier]
        tool = {
            "name": TOOL_NAME,
            "description": f"Submit the complete result as {response_model.__name__}, in ONE call.",
            "input_schema": response_model.model_json_schema(),
        }
        messages: list[dict] = [{"role": "user", "content": user}]
        usage = LLMUsage(agent=agent, model=model)
        start = time.perf_counter()
        error = ""

        try:
            for attempt in range(1, self.cfg.validation_retries + 2):
                response = self._create(
                    model, system, messages, tool, max_tokens or self.cfg.max_tokens
                )
                usage.add(response.usage)
                calls = [b for b in response.content if b.type == "tool_use"]

                if not calls:
                    error = "The response did not call the submit tool."
                elif len(calls) > 1:
                    # A split answer may validate piece by piece but be incomplete - ask for one call.
                    error = f"submit was called {len(calls)} times; call it exactly once with the complete result."
                else:
                    try:
                        result = response_model.model_validate(calls[0].input)
                        usage.latency_ms = int((time.perf_counter() - start) * 1000)
                        log.info("llm_call", **usage.model_dump())
                        return result, usage
                    except ValidationError as exc:
                        error = str(exc)

                log.warning(
                    "llm_invalid_output",
                    agent=agent,
                    attempt=attempt,
                    error=error[:300],
                )
                messages.append({"role": "assistant", "content": response.content})
                if not calls:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"You must call the {TOOL_NAME} tool.",
                        }
                    )
                else:
                    # The API requires a tool_result for EVERY tool_use block in the previous message.
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": call.id,
                                    "is_error": True,
                                    "content": f"Invalid: {error}\nCall {TOOL_NAME} once with the complete, corrected result.",
                                }
                                for call in calls
                            ],
                        }
                    )
            raise LLMError(
                f"{agent}: output still invalid after {usage.attempts} attempts: {error[:300]}"
            )
        except LLMError:
            raise
        except Exception as exc:
            log.error("llm_failed", agent=agent, model=model, error=str(exc))
            raise LLMError(f"{agent}: {exc}") from exc

    def _create(
        self, model: str, system: str, messages: list[dict], tool: dict, max_tokens: int
    ):
        """Force the tool when the model allows it; otherwise fall back to 'auto' and remember."""
        force = model not in self._no_forced_tool
        try:
            return self._call(model, system, messages, tool, max_tokens, force)
        except Exception as exc:
            if force and _forced_tool_unsupported(exc):
                self._no_forced_tool.add(model)
                log.info("tool_choice_fallback", model=model, to="auto")
                return self._call(model, system, messages, tool, max_tokens, False)
            raise

    @retry(
        retry=retry_if_exception_type(TRANSIENT_ERRORS),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    def _call(
        self,
        model: str,
        system: str,
        messages: list[dict],
        tool: dict,
        max_tokens: int,
        force: bool = True,
    ):
        optional = {}
        if self.cfg.temperature is not None:  # only send when configured
            optional["temperature"] = self.cfg.temperature
        return self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system + SUBMIT_INSTRUCTION,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=messages,
            tools=[tool],
            tool_choice={"type": "tool", "name": TOOL_NAME}
            if force
            else {"type": "auto"},
            **optional,
        )
