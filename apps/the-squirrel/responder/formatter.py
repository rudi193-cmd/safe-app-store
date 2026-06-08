from datetime import datetime

def result_block(title: str, content: str) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"\n---\n**[{ts}] {title}**\n\n{content}\n\n---\n"

def acorn_card(source: str, title: str, body: str, url: str = None) -> str:
    link = f"\n→ [{url}]({url})" if url else ""
    return f"**[{source.upper()}]** {title}\n{body}{link}\n"

def pedigree_chart(subject_name: str, ancestors: dict) -> str:
    def fmt(n):
        p = ancestors.get(n)
        if not p:
            return "Unknown"
        name = p.get("full_name", "Unknown")
        year = p.get("birth_date", "")
        return f"{name} ({year})" if year else name

    lines = []
    pad = "    "
    if ancestors.get(4):
        lines.append(f"{pad*2}┌─ {fmt(4)}")
    if ancestors.get(2):
        lines.append(f"{pad}┌─ {fmt(2)}")
    if ancestors.get(5):
        lines.append(f"{pad*2}└─ {fmt(5)}")
    lines.append(f"{subject_name} ──────┤")
    if ancestors.get(6):
        lines.append(f"{pad*2}┌─ {fmt(6)}")
    if ancestors.get(3):
        lines.append(f"{pad}└─ {fmt(3)}")
    if ancestors.get(7):
        lines.append(f"{pad*2}└─ {fmt(7)}")
    return "```\n" + "\n".join(lines) + "\n```"
