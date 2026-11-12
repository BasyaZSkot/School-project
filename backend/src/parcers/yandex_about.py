"""Read the product's About widget from JSON already present in public HTML."""
from html.parser import HTMLParser
import json

from .product_data import MAX_SPECIFICATIONS


class _AboutParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.capture = False
        self.parts = []
        self.full_specs = []
        self.fallback_specs = []
        self.description = None

    def handle_starttag(self, tag, attrs):
        if tag == "noframes" and dict(attrs).get("data-apiary") == "patch":
            self.capture = True
            self.parts = []

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag != "noframes" or not self.capture:
            return
        self.capture = False
        try:
            document = json.loads("".join(self.parts))
        except (TypeError, ValueError):
            return
        widgets = document.get("widgets", {}) if isinstance(document, dict) else {}
        if not isinstance(widgets, dict):
            return
        for name, paths in widgets.items():
            if not isinstance(paths, dict):
                continue
            for path, props in paths.items():
                if not isinstance(props, dict) or not str(path).startswith("/content/page/content/"):
                    continue
                if name == "@card/AboutFullSpecsListV2":
                    groups = props.get("specs")
                    for group in groups if isinstance(groups, list) else []:
                        spec = group.get("specs") if isinstance(group, dict) else None
                        if not isinstance(spec, dict):
                            continue
                        full = spec.get("full") or spec.get("compact") or {}
                        rows = full.get("list", []) if isinstance(full, dict) else []
                        if isinstance(rows, list):
                            self.full_specs.extend(rows[:MAX_SPECIFICATIONS])
                elif name == "@card/AboutSpecV2":
                    self.fallback_specs.append(props)
                elif name == "@card/AboutDescriptionV2" and not self.description:
                    text = props.get("fullDescription") or props.get("shortDescription")
                    if isinstance(text, str) and text.strip():
                        reader = _DescriptionParser()
                        reader.feed(text)
                        self.description = " ".join(reader.parts)[:5000] or None


class _DescriptionParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def extract_yandex_about(html):
    parser = _AboutParser()
    parser.feed(html)
    parser.close()
    rows, seen = [], set()
    for spec in parser.full_specs + parser.fallback_specs:
        if not isinstance(spec, dict):
            continue
        name, value = spec.get("name"), spec.get("value")
        if not isinstance(name, str) or not isinstance(value, (str, int, float)):
            continue
        name, value = " ".join(name.split())[:120], " ".join(str(value).split())[:500]
        if not name or not value or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        rows.append({"name": name, "value": value})
        if len(rows) >= MAX_SPECIFICATIONS:
            break
    return {"specifications": rows, "description": parser.description}
