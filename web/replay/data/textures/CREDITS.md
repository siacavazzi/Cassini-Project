# Texture credits

Maps come from CelestiaProject/CelestiaContent (GitHub); `tools/make_textures.py` in the texture study
(`/mnt/project-files/textures`) resized them into the 1k/2k/4k WebP tiers. Credit lines below are taken from
Celestia's `.license` files and README.

| Body | File | Built from | Licence |
|---|---|---|---|
| Saturn | saturn.webp | Cassini imagery, Björn Jónsson; recoloured by Askaniy Anpilogov | CC BY 3.0 |
| Rings | rings/saturn_rings.png | Björn Jónsson ring data (Celestia composite) | none stated |
| Mimas, Enceladus, Tethys, Dione, Iapetus | mimas.webp … | Paul Schenk's Cassini colour maps (NASA/JPL/LPI) | none stated |
| Rhea | rhea.webp | Schenk map and Björn Jónsson albedo | none stated |
| Titan | titan.webp | Cassini haze images, Gordan Ugarković, Kevin M. Gill, ShadowDragon777, AstroChara | CC BY 4.0 |
| Titan surface | titan_surface.webp | Cassini VIMS and ISS map (Seignovert et al. 2019), radar lakes | CC BY 3.0 |
| Hyperion | hyperion.webp, models/hyperion | reprojected Cassini imagery (ItzImcool); shape Thomas et al., PDS | CC BY 4.0; shape CC0 |
| Phoebe | phoebe.webp, models/phoebe | John van Vliet; shape Gaskell, PDS | none stated |
| Jupiter | jupiter.webp | Cassini 2000 flyby and Juno data, recoloured by Askaniy | CC BY 3.0 |
| Venus | venus.webp | cloud tops by Björn Jónsson, recoloured by FarGetaNik | none stated |
| Earth | earth.webp | "Mappamondo" (earthstartsbeating.com), Natural Earth II (Tom Patterson), NASA Blue Marble Next Generation | none stated |
| Moon | moon.webp | Celestia's lunar map (NASA data) | none stated |
| Io | io.webp | ItzImcool, AstroChara; NASA/JPL-Caltech/ASI/USGS; NASA/JPL/SwRI/MSSS/Gerald Eichstädt/Jason Perry/John Rogers | CC BY 4.0 |
| Europa | europa.webp | John van Vliet | none stated |
| Ganymede | ganymede.webp | Askaniy Anpilogov; NASA/JPL-Caltech/ASI/USGS; Björn Jónsson; NASA/JPL-Caltech/SwRI/MSSS/Brian Swift | CC BY 3.0 |
| Callisto | callisto.webp | Askaniy, from John van Vliet's map | none stated |

The CC BY maps are fine on a public site with this credit list. The maps marked "none stated" are reworks of
NASA/JPL and other material without a licence file; before a public launch, rebuild them from public-domain
originals (USGS Astrogeology mosaics, NASA Blue Marble, Björn Jónsson's own releases) with the same tool.

## Star sky

| What | File | Built from | Licence |
|---|---|---|---|
| Stars and Milky Way | sky/sky_2k.webp, sky_4k.webp, sky_8k.webp | NASA SVS "Deep Star Maps 2020" (https://svs.gsfc.nasa.gov/4851), `starmap_2020_8k.exr`: Hipparcos, Tycho-2 and Gaia DR2 stars plus the Milky Way, equirectangular in J2000 (RA 0h in the middle, RA growing to the left) | NASA, public domain. Credit: NASA/Goddard Space Flight Center Scientific Visualization Studio. Gaia DR2: ESA/Gaia/DPAC. |

`web/replay/make_sky.py` turns the linear HDR map into the three WebP tiers: it averages down in linear light, maps
brightness with an exposure curve fitted to NASA's own display thumbnail (`starmap_2020_4k_print.jpg`), and checks
the orientation against 15 bright stars.
