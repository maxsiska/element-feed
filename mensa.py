"""Read dated Mensa X dish names from the Studierendenwerk's public menu."""

from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.request import Request, urlopen


MENU_URL = "https://www.studierendenwerk-bielefeld.de/essen-trinken/speiseplan/"


class MenuUnavailable(ValueError):
    """The requested day's Mensa X dishes could not be retrieved."""


@dataclass(frozen=True)
class Menu:
    day: date
    mains: tuple[str, ...]
    sides: tuple[str, ...]


class _MenuParser(HTMLParser):
    def __init__(self, day):
        super().__init__(convert_charrefs=True)
        self.day = day.strftime("%Y%m%d")
        self.divs = []
        self.lists = []
        self.mensa_select = False
        self.selected_mensa = None
        self.found_day = False
        self.mains = []
        self.sides = []
        self.capture = None
        self.capture_depth = 0
        self.parts = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        classes = set(attrs.get("class", "").split())
        # Track div/ul scopes only: the source omits many </li> and </p> tags.
        if tag == "div":
            self.divs.append((attrs, classes))
        elif tag == "ul":
            self.lists.append(classes)
        elif tag == "select":
            self.mensa_select = "menuMensaSelect" in classes
        elif tag == "option" and self.mensa_select and "selected" in attrs:
            self.selected_mensa = attrs.get("value")

        if self.capture:
            if tag == self.capture[0]:
                self.capture_depth += 1
            if tag == "br":
                self.parts.append(" ")
            return

        if not any(a.get("id") == "menuContainer" for a, _ in self.divs):
            return
        day = next((a.get("data-selector") for a, c in reversed(self.divs)
                    if "menuDay" in c), None)
        if day != self.day:
            return
        self.found_day = True
        scope = set().union(*(c for _, c in self.divs))
        # Modal dialogs repeat dish names and contain extra, optional toppings.
        if "modal" in scope:
            return
        target = None
        if (tag == "h3" and "menuItem__headline" in classes
                and "menuItem--mainmenu" in scope):
            target = self.mains
        elif (tag == "span" and "menuItem__sidedish__label" in classes
              and "menuItem--sidedish" in scope
              and any("menuItem__sidedishes" in c for c in self.lists)):
            # The soup is also a sidedish-style card on the website.
            target = self.sides if "menuLine--MBeilagen" in scope else self.mains
        if target is not None:
            self.capture = (tag, target)
            self.capture_depth = 1
            self.parts = []

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if self.capture and tag == self.capture[0]:
            self.capture_depth -= 1
            if self.capture_depth == 0:
                name = " ".join("".join(self.parts).split())
                target = self.capture[1]
                small_portion = name.casefold().endswith((" klein", " (klein)"))
                if name and not small_portion and name not in target:
                    target.append(name)
                self.capture = None
        if tag == "div" and self.divs:
            self.divs.pop()
        elif tag == "ul" and self.lists:
            self.lists.pop()
        elif tag == "select":
            self.mensa_select = False


def parse_menu(html, day):
    parser = _MenuParser(day)
    parser.feed(html)
    parser.close()
    # Like the reference project, fetch the default page, but verify its canteen
    # selection so a website default change cannot silently give us Sowls.
    if parser.selected_mensa != "13":
        raise MenuUnavailable("The page is not confirmed as Bielefeld Mensa X (13)")
    if not parser.found_day or not parser.mains:
        raise MenuUnavailable(f"No Mensa X dishes found for {day.isoformat()}")
    return Menu(day, tuple(parser.mains), tuple(parser.sides))


def fetch_menu(day):
    request = Request(MENU_URL, headers={"User-Agent": "element-feed/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            html = response.read().decode(response.headers.get_content_charset() or "utf-8")
        return parse_menu(html, day)
    except (OSError, UnicodeError) as exc:
        raise MenuUnavailable(f"Could not fetch the menu: {exc}") from exc
