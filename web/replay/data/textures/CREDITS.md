# Texture credits

The credit for every map, ring and shape file here lives in one list, `web/cassini-os/src/credits.json` (group
"Surface maps and shapes"), which Cassini OS shows in About Cassini OS > Credits. Add a new file there, under `files`
of its entry; `web/cassini-os/src/build.py` refuses to build while a file in this folder has no entry.

Maps come from CelestiaProject/CelestiaContent (GitHub); `tools/make_textures.py` in the texture study
(`/mnt/project-files/textures`) resized them into the 1k/2k/4k WebP tiers. Credit lines are taken from
Celestia's `.license` files and README.

The CC BY maps are fine on a public site with this credit list. The maps marked "none stated" are reworks of
NASA/JPL and other material without a licence file; before a public launch, rebuild them from public-domain
originals (USGS Astrogeology mosaics, NASA Blue Marble, Björn Jónsson's own releases) with the same tool.

## Star sky

The sky files in `sky/` are credited in `credits.json` (group "Sky", NASA SVS "Deep Star Maps 2020",
https://svs.gsfc.nasa.gov/4851).

`web/replay/make_sky.py` turns the linear HDR map into the three WebP tiers: it averages down in linear light, maps
brightness with an exposure curve fitted to NASA's own display thumbnail (`starmap_2020_4k_print.jpg`), and checks
the orientation against 15 bright stars.
