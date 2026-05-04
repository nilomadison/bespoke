import httpx

from src.config import settings


class LLMError(Exception):
    def __init__(self, message: str, status_code: int, body: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class LLMClient:
    """Thin async wrapper around OpenRouter's chat completions endpoint."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.openrouter_base_url,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://github.com/local/bespoke",
                "X-Title": "Bespoke Resume Tool",
            },
            timeout=120.0,
        )

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        response = await self._client.post(
            "/chat/completions",
            json={
                "model": model or settings.default_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        if response.status_code != 200:
            raise LLMError(
                f"OpenRouter returned {response.status_code}",
                status_code=response.status_code,
                body=response.text,
            )
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def close(self) -> None:
        await self._client.aclose()
