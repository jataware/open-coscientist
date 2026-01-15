"""
LLM calling utilities using litellm.

Provides a clean interface for calling LLMs with proper error handling
and JSON parsing.
"""

import asyncio
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
import warnings

import jsonschema
from jsonschema.exceptions import ValidationError
import litellm

from .cache import get_cache

logger = logging.getLogger(__name__)


# suppress Pydantic serialization warnings from LiteLLM globally
# these occur when LiteLLM response objects (Pydantic models) are serialized
# and have mismatched field counts between streaming/non-streaming responses
warnings.filterwarnings("ignore", message=r".*Pydantic serializer warnings.*", category=UserWarning)


def attempt_json_repair(
    json_str: str, allow_major_repairs: bool = False
) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Attempt to repair common JSON syntax errors from LLM outputs.

    With json_schema response formats, most responses should be valid JSON.
    This function first tries to parse as-is, and only attempts repairs if needed.

    Args:
        json_str: Potentially malformed JSON string
        allow_major_repairs: If True, attempt major repairs (indicate truncation).
                           If False, only attempt minor repairs (safe syntax fixes).

    Returns:
        Tuple of (parsed JSON dict if successful, was_major_repair: bool)
        Returns (None, False) if all repair attempts failed
    """
    # First, try parsing as-is (should work for json_schema responses)
    try:
        result = json.loads(json_str)
        if isinstance(result, dict):
            return result, False
    except json.JSONDecodeError:
        # JSON is malformed, proceed with repair strategies
        pass

    def close_truncated_json(s: str) -> str:
        """Try to close truncated JSON by adding missing braces/brackets."""
        # Count open vs closed braces and brackets
        open_braces = s.count("{") - s.count("}")
        open_brackets = s.count("[") - s.count("]")

        # Enhanced unterminated string detection
        # Check if the string ends mid-value (unterminated string)
        stripped = s.rstrip()

        # Pattern 1: Ends with opening quote after colon/comma (e.g., ':"text)
        if re.search(r'[:,]\s*"[^"]*$', stripped):
            s = s + '"'
            logger.debug("repaired: unterminated string after colon/comma")

        # Pattern 2: Ends with partial field name (e.g., '"field_na)
        elif re.search(r'"\w+$', stripped):
            # Find if we're in a string literal or field name
            # Count quotes before this position to determine context
            before_partial = stripped[:-20] if len(stripped) > 20 else ""
            quote_count = before_partial.count('"')
            if quote_count % 2 == 1:  # Odd number = we're inside a string
                s = s + '"'
                logger.debug("repaired: unterminated field name/string")

        # Pattern 3: Ends mid-array without closing (e.g., '"item1", "item2)
        elif stripped.endswith(",") or (stripped[-1].isalnum() and "[" in stripped):
            # Likely truncated mid-array or mid-value
            # Try to close intelligently based on context
            last_open_bracket = stripped.rfind("[")
            last_close_bracket = stripped.rfind("]")
            if last_open_bracket > last_close_bracket:
                # We're inside an unclosed array
                # Check if we need to close a string first
                after_bracket = stripped[last_open_bracket:]
                quote_count = after_bracket.count('"')
                if quote_count % 2 == 1:
                    s = s + '"'
                    logger.debug("repaired: unterminated string in array")

        # Remove trailing comma if present
        s = re.sub(r",\s*$", "", s)

        # Add missing closing characters
        # Close arrays first, then objects (proper nesting)
        result = s + ("]" * open_brackets) + ("}" * open_braces)

        if open_braces > 0 or open_brackets > 0:
            logger.debug(f"repaired: added {open_brackets} ']' and {open_braces} '}}'")

        return result

    # Minor repairs (safe, don't indicate truncation)
    minor_repairs = [
        # Remove trailing commas before closing braces/brackets
        lambda s: json.loads(re.sub(r",(\s*[}\]])", r"\1", s)),
    ]

    # Major repairs (indicate truncation/incomplete, only on final retry)
    major_repairs = [
        # Close unterminated strings and truncated JSON (most common Gemini issue)
        lambda s: json.loads(close_truncated_json(s)),
        # Remove trailing commas AND close truncated JSON
        lambda s: json.loads(close_truncated_json(re.sub(r",(\s*[}\]])", r"\1", s))),
        # Aggressively remove incomplete trailing content and close JSON
        lambda s: json.loads(close_truncated_json(re.sub(r',?\s*"[^"]*$', "", s))),
        # Remove incomplete field (key OR value) and close
        lambda s: json.loads(close_truncated_json(re.sub(r'[:,]\s*"[^"]*$', "", s))),
        # Find last complete comma, truncate there, then close
        lambda s: json.loads(close_truncated_json(s[: s.rfind(",") + 1] if "," in s else s)),
        # Extract first complete JSON object using regex
        lambda s: (
            json.loads(re.search(r"\{.*\}", s, re.DOTALL).group(0))
            if re.search(r"\{.*\}", s, re.DOTALL)
            else None
        ),
    ]

    # Try minor repairs first
    for i, repair_fn in enumerate(minor_repairs):
        try:
            result = repair_fn(json_str)
            if result:
                logger.debug(f"JSON repaired using minor repair strategy {i}")
                return result, False
        except (json.JSONDecodeError, AttributeError, TypeError) as e:
            logger.debug(f"minor repair strategy {i} failed: {e}")
            continue

    # If major repairs are allowed, try them
    if allow_major_repairs:
        for i, repair_fn in enumerate(major_repairs):
            try:
                result = repair_fn(json_str)
                if result:
                    logger.warning(
                        f"JSON repaired using major repair strategy {i} (indicates truncation/incomplete response)"
                    )
                    return result, True
            except (json.JSONDecodeError, AttributeError, TypeError) as e:
                if i < 2:  # Only log for first few strategies
                    logger.debug(f"major repair strategy {i} failed: {e}")
                continue

    return None, False


def validate_json_schema(result: Dict[str, Any], json_schema: Optional[Dict[str, Any]]) -> None:
    """
    Validate parsed JSON against the provided schema.

    Args:
        result: Parsed JSON dictionary to validate
        json_schema: Optional JSON schema dict (may have nested "schema" key)

    Raises:
        ValidationError: If the result doesn't match the schema
    """
    if json_schema is None:
        # No schema provided, skip validation
        return

    # Extract actual schema from nested structure if present
    actual_schema = json_schema.get("schema", json_schema)

    try:
        jsonschema.validate(instance=result, schema=actual_schema)
        logger.debug("JSON schema validation passed")
    except ValidationError as e:
        logger.warning(f"JSON schema validation failed: {e.message}")
        logger.debug(f"validation error path: {'.'.join(str(p) for p in e.path)}")
        logger.debug(f"first 500 chars of result: {str(result)[:500]}")
        raise


def get_fallback_response(json_schema: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Get fallback placeholder data for non-critical nodes that failed.

    Args:
        json_schema: Optional JSON schema dict (may have "name" field to identify node)

    Returns:
        Placeholder data matching schema structure, or None if node is critical
    """
    if json_schema is None:
        return None

    schema_name = json_schema.get("name")

    # Non-critical nodes that can fail gracefully
    if schema_name == "proximity_analysis":
        logger.warning(
            "Proximity analysis failed after all retries. "
            "Returning fallback data to continue workflow."
        )
        return {
            "similarity_clusters": [],
            "diversity_assessment": "Analysis failed - skipping deduplication",
            "redundancy_assessment": "Analysis failed - skipping deduplication",
        }

    # Critical nodes - no fallback
    return None


async def call_llm(
    prompt: str,
    model_name: str,
    max_tokens: int = 4000,
    temperature: float = 0.7,
    force_json: bool = False,
    json_schema: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Call an LLM via litellm and return the response.

    Args:
        prompt: The prompt to send to the LLM
        model_name: Model name in litellm format (e.g., "gpt-4o-mini", "gemini/gemini-2.5-flash")
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature
        force_json: If True, try to force JSON mode (model support varies)
        json_schema: Optional JSON schema to constrain the response format

    Returns:
        String response from the LLM

    Raises:
        Exception: If the LLM call fails
    """
    # clamp temperature for gemini 3 models (requires temp >= 1.0)
    if "gemini-3" in model_name.lower() and temperature < 1.0:
        original_temp = temperature
        temperature = 1.0
        logger.debug(
            f"clamping temperature {original_temp} -> 1.0 for gemini 3 model "
            f"(gemini 3 requires temp >= 1.0 to avoid degraded performance)"
        )

    # Check cache first
    cache = get_cache()
    cached_response = cache.get(
        prompt, model_name, temperature, max_tokens,
        json_schema=json_schema, force_json=force_json
    )
    if cached_response is not None:
        logger.debug("using cached llm response")
        return cached_response["text"]

    logger.debug(f"cache miss for prompt: {prompt[:200]}{'...' if len(prompt) > 200 else ''}")

    try:
        # Build completion args
        completion_args = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "drop_params": True,
        }

        # Try to add response_format based on schema or force_json
        if json_schema:
            try:
                completion_args["response_format"] = {
                    "type": "json_schema",
                    "json_schema": json_schema,
                }
            except Exception as e:
                # Some models/providers don't support json_schema, fall back to json_object
                logger.warning(f"JSON schema not supported, falling back to json_object: {e}")
                try:
                    completion_args["response_format"] = {"type": "json_object"}
                except Exception:
                    # Some models/providers don't support this either, silently continue
                    pass
        elif force_json:
            try:
                completion_args["response_format"] = {"type": "json_object"}
            except Exception:
                # Some models/providers don't support this, silently continue
                pass

        response = await litellm.acompletion(**completion_args)

        content = response.choices[0].message.content

        if content is None or not content.strip():
            logger.error(f"LLM returned None or empty content. Response: {response}")
            raise ValueError(f"LLM returned None or empty content. Model: {model_name}")

        # Cache the response (only reached if content is valid)
        cache.set(
            prompt,
            model_name,
            temperature,
            max_tokens,
            {"text": content},
            json_schema=json_schema,
            force_json=force_json,
        )

        return content

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        logger.error(f"Model: {model_name}, max_tokens: {max_tokens}")
        raise


async def call_llm_json(
    prompt: str,
    model_name: str,
    max_tokens: int = 4000,
    temperature: float = 0.7,
    json_schema: Optional[Dict[str, Any]] = None,
    max_attempts: int = 5,
) -> Dict[str, Any]:
    """
    Call an LLM and parse the response as JSON with validation and retry logic.

    Args:
        prompt: The prompt to send to the LLM
        model_name: Model name in litellm format
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature
        json_schema: Optional JSON schema to constrain the response format
        max_attempts: Maximum number of retry attempts (default 5)

    Returns:
        Parsed JSON response as a dictionary

    Raises:
        json.JSONDecodeError: If response is not valid JSON after all repair attempts (for critical nodes)
        ValidationError: If response doesn't match schema after all retries (for critical nodes)
        Exception: If the LLM call fails or returns empty response
    """
    # Check cache first
    cache = get_cache()
    cached_response = cache.get(
        prompt, model_name, temperature, max_tokens, json_schema=json_schema
    )
    if cached_response is not None:
        logger.debug("using cached llm json response")
        return cached_response

    logger.debug(f"cache miss for prompt: {prompt[:200]}{'...' if len(prompt) > 200 else ''}")
    last_error = None
    last_response_text = None
    original_prompt = prompt  # save original for retries with feedback

    for attempt in range(1, max_attempts + 1):
        is_final_attempt = attempt == max_attempts

        if attempt > 1:
            logger.debug(f"retrying llm call (attempt {attempt}/{max_attempts})")

        try:
            # Call LLM
            response_text = await call_llm(
                prompt,
                model_name,
                max_tokens,
                temperature,
                force_json=True if not json_schema else False,
                json_schema=json_schema,
            )

            # Check for None or empty response
            if not response_text:
                logger.error("LLM returned None or empty response")
                raise ValueError(
                    "LLM returned None or empty response. Check API keys, rate limits, and model availability."
                )

            # Try to extract JSON from markdown code blocks if present
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            last_response_text = response_text

            # Step 1: Try simple parse first
            result = None
            parse_error = None
            try:
                result = json.loads(response_text)
                if not isinstance(result, dict):
                    parse_error = ValueError("Parsed JSON is not a dictionary")
                    result = None
            except json.JSONDecodeError as e:
                parse_error = e
                result = None

            # Step 2: If parsing succeeded, validate schema
            if result is not None:
                if json_schema is not None:
                    try:
                        validate_json_schema(result, json_schema)
                        # Success! Cache and return
                        cache.set(
                            prompt,
                            model_name,
                            temperature,
                            max_tokens,
                            result,
                            json_schema=json_schema,
                        )
                        return result
                    except ValidationError as e:
                        last_error = e
                        logger.warning(
                            f"Schema validation failed on attempt {attempt}: {e.message}"
                        )

                        # add validation feedback to prompt for next retry
                        if not is_final_attempt:
                            error_path = ".".join(str(p) for p in e.path) if e.path else "root"
                            validation_feedback = f"\n\n--- VALIDATION ERROR FROM PREVIOUS ATTEMPT ---\nError: {e.message}\nLocation: {error_path}\nPlease ensure your JSON output strictly matches the required schema structure.\n---"
                            prompt = original_prompt + validation_feedback
                            logger.debug("added validation feedback to retry prompt")

                        # Retry on validation failure
                        continue
                else:
                    # No schema, parsing succeeded - we're done
                    cache.set(
                        prompt, model_name, temperature, max_tokens, result, json_schema=json_schema
                    )
                    return result

            # Step 3: Parsing failed, attempt repairs
            was_major_repair = False
            if parse_error is not None:
                # Attempt repairs (minor only unless final attempt)
                result, was_major_repair = attempt_json_repair(
                    response_text,
                    allow_major_repairs=is_final_attempt
                )

                if result is not None:
                    # Repair succeeded, validate schema if provided
                    if json_schema is not None:
                        try:
                            validate_json_schema(result, json_schema)
                            # Success! Cache and return
                            cache.set(
                                prompt,
                                model_name,
                                temperature,
                                max_tokens,
                                result,
                                json_schema=json_schema,
                            )
                            return result
                        except ValidationError as e:
                            last_error = e
                            logger.warning(
                                f"Schema validation failed after repair on attempt {attempt}: {e.message}"
                            )

                            # add validation feedback to prompt for next retry
                            if not is_final_attempt:
                                error_path = ".".join(str(p) for p in e.path) if e.path else "root"
                                validation_feedback = f"\n\n--- VALIDATION ERROR FROM PREVIOUS ATTEMPT ---\nError: {e.message}\nLocation: {error_path}\nPlease ensure your JSON output strictly matches the required schema structure.\n---"
                                prompt = original_prompt + validation_feedback
                                logger.debug(
                                    "added validation feedback to retry prompt after repair"
                                )

                            # Retry on validation failure
                            continue
                    else:
                        # No schema, repair succeeded - we're done
                        cache.set(
                            prompt,
                            model_name,
                            temperature,
                            max_tokens,
                            result,
                            json_schema=json_schema,
                        )
                        return result

                # If major repair was needed but we're not on final attempt, retry immediately
                if was_major_repair and not is_final_attempt:
                    logger.info("Major repair needed (truncation detected), retrying immediately")
                    continue

            # All repairs exhausted for this attempt
            last_error = parse_error or ValueError("All repair strategies failed")

        except Exception as e:
            last_error = e
            logger.error(f"LLM call failed on attempt {attempt}: {e}")
            if is_final_attempt:
                raise

    # All retries exhausted
    # Check for fallback for non-critical nodes
    fallback = get_fallback_response(json_schema)
    if fallback is not None:
        logger.warning("Returning fallback data for non-critical node after all retries exhausted")
        return fallback

    # No fallback available - raise appropriate error
    if last_response_text:
        # Log the full response for debugging
        logger.error("Failed to parse JSON response after all repair attempts.")
        logger.error(f"Response length: {len(last_response_text)} chars")
        logger.error(f"First 500 chars: {last_response_text[:500]}")
        logger.error(f"Last 500 chars: {last_response_text[-500:]}")

        # Log middle section too (where errors often are)
        if len(last_response_text) > 1000:
            mid_point = len(last_response_text) // 2
            logger.error(
                f"Middle 500 chars (around char {mid_point}): {last_response_text[mid_point-250:mid_point+250]}"
            )

        # Try to find where JSON is broken
        try:
            # Count braces
            open_braces = last_response_text.count("{")
            close_braces = last_response_text.count("}")
            logger.error(f"Brace count: {{ = {open_braces}, }} = {close_braces}")

            # Try to find first JSON error position
            for i in range(0, len(last_response_text), 100):
                chunk = last_response_text[: i + 100]
                try:
                    json.loads(chunk)
                except json.JSONDecodeError as e:
                    if i > len(last_response_text) - 200:  # Near the end
                        logger.error(f"JSON error near position {e.pos}: {e.msg}")
                        logger.error(
                            f"Context around error: ...{last_response_text[max(0,e.pos-100):e.pos+100]}..."
                        )
                        break
        except Exception as debug_err:
            logger.error(f"Error during debugging: {debug_err}")

    # Raise appropriate error
    if isinstance(last_error, ValidationError):
        raise ValidationError(
            f"Schema validation failed after {max_attempts} attempts: {last_error.message}",
            instance=last_error.instance,
            schema=last_error.schema,
            schema_path=last_error.schema_path,
            path=last_error.path,
        )
    elif isinstance(last_error, json.JSONDecodeError):
        raise json.JSONDecodeError(
            f"Could not parse LLM response as JSON after {max_attempts} attempts",
            last_response_text or "",
            last_error.pos if hasattr(last_error, "pos") else 0,
        )
    else:
        raise json.JSONDecodeError(
            f"Could not parse LLM response as JSON after {max_attempts} attempts",
            last_response_text or "",
            0,
        )


async def call_llm_with_tools(
    prompt: str,
    model_name: str,
    tools: List[Dict[str, Any]],
    tool_executor: Callable,
    max_tokens: int = 8000,
    temperature: float = 0.7,
    max_iterations: int = 10,
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Call an LLM with tool access and handle tool execution loop.

    This function implements an agent loop where the LLM can call tools,
    see the results, and continue iterating until it produces a final response.

    Args:
        prompt: The initial user prompt
        model_name: Model name in litellm format
        tools: List of tools in OpenAI format
        tool_executor: Async callable that executes tool calls and returns tool response messages
        max_tokens: Maximum tokens per LLM call
        temperature: Sampling temperature
        max_iterations: Maximum number of LLM calls (prevents infinite loops)

    Returns:
        Tuple of (final_response_text, complete_message_history)

    Raises:
        Exception: If the LLM call fails or max iterations reached
    """
    # clamp temperature for gemini 3 models (requires temp >= 1.0)
    if "gemini-3" in model_name.lower() and temperature < 1.0:
        original_temp = temperature
        temperature = 1.0
        logger.debug(
            f"clamping temperature {original_temp} -> 1.0 for gemini 3 model "
            f"(gemini 3 requires temp >= 1.0 to avoid degraded performance)"
        )

    # Check cache first
    cache = get_cache()
    cached_response = cache.get(prompt, model_name, temperature, max_tokens, tools=tools)
    if cached_response is not None:
        logger.debug("using cached llm tool call response")
        return cached_response["final_response"], cached_response["message_history"]

    logger.debug(f"cache miss for prompt: {prompt[:200]}{'...' if len(prompt) > 200 else ''}")

    messages = [{"role": "user", "content": prompt}]

    for iteration in range(max_iterations):
        logger.debug(f"llm tool call iteration {iteration + 1}/{max_iterations}")

        try:
            # Call LLM with tools
            response = await litellm.acompletion(
                model=model_name,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                drop_params=True,
            )

            message = response.choices[0].message

            # Convert message to dict format for history
            message_dict = {
                "role": message.role,
                "content": message.content,
            }

            # Add tool calls if present
            if hasattr(message, "tool_calls") and message.tool_calls:
                message_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]

            messages.append(message_dict)

            # Check if LLM wants to call tools
            if hasattr(message, "tool_calls") and message.tool_calls:
                logger.debug(f"llm requested {len(message.tool_calls)} tool calls")

                # Execute all tool calls in parallel
                tool_results = await asyncio.gather(
                    *[tool_executor(tc) for tc in message.tool_calls]
                )

                # Add tool results to message history
                messages.extend(tool_results)

                # Continue loop - LLM will see tool results and respond
                continue
            else:
                # No tool calls - this is the final response
                final_content = message.content if message.content else ""

                # Validate response before caching
                if not final_content.strip():
                    logger.error("LLM returned empty final response in tool call loop")
                    raise ValueError(f"LLM returned empty final response. Model: {model_name}")

                logger.debug(f"llm finished after {iteration + 1} iterations")

                # Cache the successful result (only reached if content is valid)
                cache.set(
                    prompt,
                    model_name,
                    temperature,
                    max_tokens,
                    {"final_response": final_content, "message_history": messages},
                    tools=tools,
                )

                return final_content, messages

        except Exception as e:
            logger.error(f"Error in LLM tool call loop (iteration {iteration + 1}): {e}")
            raise

    # Max iterations reached
    logger.warning(f"Max iterations ({max_iterations}) reached in tool call loop")
    raise RuntimeError(f"LLM tool call loop exceeded max iterations ({max_iterations})")
