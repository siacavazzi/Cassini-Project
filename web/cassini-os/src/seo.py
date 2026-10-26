"""
What search engines and link previews read (site.json): the page's title, description, share card, canonical
address and structured data, the About page (landing.html, written to about/index.html), robots.txt and sitemap.xml.

site.json "url" is the public address the site is served from (https://..., ending in /); CASSINI_SITE_URL overrides
it at build time. While it is empty (the Mini on home Wi-Fi) the pages carry everything that does not need it, and
robots.txt has no sitemap line; with it set, the canonical links, og:url, absolute share images and sitemap.xml are
written too. build.py calls head() for index.html and write_files() after it.
"""
import html, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load():
    site = json.load(open(os.path.join(HERE, "site.json")))
    url = os.environ.get("CASSINI_SITE_URL", site.get("url") or "").strip()
    site["url"] = url.rstrip("/") + "/" if url else ""
    return site


def _abs(site, path, depth):
    """path on the site (no leading /), absolute when the site's address is known, else relative from depth folders down"""
    return site["url"] + path if site["url"] else "../" * depth + path


def head(site, path="", title=None, description=None, depth=0, kind="app"):
    """The <title> and every tag after it for the page at path ("" for the app, "about/" for the About page)."""
    esc = lambda s: html.escape(s, quote=True)
    title = title or site["title"]
    description = description or site["description"]
    image = _abs(site, site["image"], depth)
    tags = [
        f"<title>{esc(title)}</title>",
        f'<meta name="description" content="{esc(description)}">',
        f'<meta name="author" content="{esc(site["author"])}">',
        '<meta name="robots" content="index, follow, max-image-preview:large">',
        f'<link rel="icon" href="{"../" * depth}favicon.svg" type="image/svg+xml">',
        f'<link rel="icon" href="{"../" * depth}favicon-48.png" sizes="48x48" type="image/png">',
        f'<link rel="apple-touch-icon" href="{"../" * depth}apple-touch-icon.png">',
        '<meta name="theme-color" content="#000000">',
    ]
    if site["url"]:
        tags.append(f'<link rel="canonical" href="{esc(site["url"] + path)}">')
    tags += [
        '<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{esc(site["name"])}">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        f'<meta property="og:image" content="{esc(image)}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        f'<meta property="og:image:alt" content="{esc(site["image_alt"])}">',
        '<meta property="og:locale" content="en_US">',
    ]
    if site["url"]:
        tags.append(f'<meta property="og:url" content="{esc(site["url"] + path)}">')
    tags += [
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{esc(title)}">',
        f'<meta name="twitter:description" content="{esc(description)}">',
        f'<meta name="twitter:image" content="{esc(image)}">',
        f'<meta name="twitter:image:alt" content="{esc(site["image_alt"])}">',
    ]
    # structured data: the app itself as a WebApplication; the About page as the page about it
    app = {
        "@type": "WebApplication",
        "name": site["name"],
        "description": site["description"],
        "applicationCategory": "EducationalApplication",
        "operatingSystem": "Any (a web browser with WebGL)",
        "browserRequirements": "Requires JavaScript and WebGL",
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        "isAccessibleForFree": True,
        "inLanguage": "en",
        "image": image,
        "author": {"@type": "Person", "name": site["author"], "url": site["author_url"]},
        "about": [
            {"@type": "Thing", "name": "Cassini-Huygens", "sameAs": "https://en.wikipedia.org/wiki/Cassini%E2%80%93Huygens"},
            {"@type": "Thing", "name": "Saturn", "sameAs": "https://en.wikipedia.org/wiki/Saturn"},
        ],
    }
    if site["url"]:
        app["url"] = site["url"]
    data = app if kind == "app" else {
        "@type": "AboutPage", "name": title, "description": description, "inLanguage": "en", "mainEntity": app,
        **({"url": site["url"] + path} if site["url"] else {}),
    }
    data = {"@context": "https://schema.org", **data}
    tags.append('<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + "</script>")
    return "\n".join(tags)


def noscript(site):
    """What the app page says without JavaScript: what Cassini OS is, and the way to the About page."""
    return (
        '<noscript><div style="max-width:640px;margin:80px auto;padding:0 16px;font:15px/1.6 -apple-system,\'Lucida Grande\',Verdana,sans-serif;color:#e8ecf2">'
        f'<h1 style="font-weight:normal">{html.escape(site["name"])}</h1>'
        f'<p>{html.escape(site["description"])}</p>'
        '<p>Cassini OS is a 3D page and needs JavaScript and WebGL. <a href="about/" style="color:#8ab6ff">Read about the project</a>.</p>'
        "</div></noscript>"
    )


def write_files(site):
    """about/index.html, robots.txt and (with the site's address) sitemap.xml, next to index.html"""
    page = open(os.path.join(HERE, "landing.html")).read()
    title = f"About {site['name']}: the Cassini mission to Saturn, replayed with its pictures"
    desc = ("What Cassini OS is: a free replay of the Cassini-Huygens mission in the browser, where the spacecraft flies "
            "its real path and the camera windows show the pictures it took of Saturn, Titan, Enceladus and the other "
            "moons, calibrated and in color.")
    assert page.count("<!--HEAD-->") == 1
    os.makedirs(os.path.join(ROOT, "about"), exist_ok=True)
    open(os.path.join(ROOT, "about", "index.html"), "w").write(
        page.replace("<!--HEAD-->", head(site, "about/", title, desc, depth=1, kind="about")))
    robots = "User-agent: *\nAllow: /\nDisallow: /flags/\nDisallow: /export/\nDisallow: /replay/\n"
    sitemap = os.path.join(ROOT, "sitemap.xml")
    if site["url"]:
        robots += f"\nSitemap: {site['url']}sitemap.xml\n"
        open(sitemap, "w").write(
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"  <url><loc>{html.escape(site['url'] + p)}</loc></url>\n" for p in ("", "about/"))
            + "</urlset>\n")
    elif os.path.exists(sitemap):
        os.remove(sitemap)
    open(os.path.join(ROOT, "robots.txt"), "w").write(robots)
