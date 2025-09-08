from typing import List
def chunk_text(text: str, chunk_size: int = 1500, overlap: int = 200) -> List[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks, start, n = [], 0, len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end == n: break
        start = max(0, end - overlap)
    return chunks
