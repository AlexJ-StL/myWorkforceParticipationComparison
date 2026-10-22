import pathlib
import re
import sys

# Force UTF-8 encoding on Windows console stdout/stderr
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def check_markdown_links():
    docs = pathlib.Path(".")
    broken = []

    # Pattern to match [label](relative_link)
    link_pattern = re.compile(r"\[.*?\]\((.*?)\)")

    for f in docs.rglob("*.md"):
        # Skip dependency directories
        if any(part.startswith((".", "_")) for part in f.parts):
            continue

        content = f.read_text(encoding="utf-8")
        for match in link_pattern.finditer(content):
            link = match.group(1)

            # Skip external URLs, mailto links, and anchor-only links
            if link.startswith(("http://", "https://", "mailto:", "#")):
                continue

            # Strip internal section anchors (e.g., path.md#section -> path.md)
            target_path = link.split("#")[0]
            if not target_path:
                continue

            resolved = f.parent / target_path
            if not resolved.exists():
                broken.append((f, link))

    if broken:
        print("✖ Broken documentation links found:")
        for source, link in broken:
            print(f"  - {source}: {link}")
        sys.exit(1)
    else:
        print("✔ All documentation links resolved.")
        sys.exit(0)


if __name__ == "__main__":
    check_markdown_links()
