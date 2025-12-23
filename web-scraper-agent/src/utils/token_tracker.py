import tiktoken

class TokenTracker:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.encoding = tiktoken.encoding_for_model(model)
        self.total = 0

    def count(self, text: str) -> int:
        tokens = len(self.encoding.encode(text))
        self.total += tokens
        return tokens

    def print_summary(self, start_time: float):
        import time
        elapsed = time.time() - start_time
        cost = (self.total / 1_000_000) * 0.15
        print("="*50)
        print(f"⏱️  Time taken: {elapsed:.1f}s ({elapsed/60:.1f}min)")
        print(f"🪙  Tokens used: {self.total:,}")
        print(f"💰  Est. cost: ${cost:.4f}")
        print("="*50)