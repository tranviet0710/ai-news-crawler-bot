PROMPT = (
    "Ban la mot chuyen gia AI. Hay doc tin tuc sau. Neu no noi ve viec ra mat model moi, "
    "AI agents, hoac cap nhat quan trong ve AI trong lap trinh (OpenAI, Anthropic, Google...), "
    "hay tra ve 1 ban tom tat ngan gon bang tieng Viet toi da 3 dong. "
    "Neu khong lien quan hoac la tin rac, tra ve dung chuoi SKIP."
)


def build_news_prompt(title: str, source: str, summary: str, url: str) -> str:
    return (
        f"Title: {title}\n"
        f"Source: {source}\n"
        f"Summary: {summary}\n"
        f"URL: {url}"
    )
