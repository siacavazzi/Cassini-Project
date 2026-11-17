# Raw-pointing movies stabilized by default (audit finding 4)

Before/after clips: left is main as drawn today, right is this branch. Shake is how much the frame-to-frame shift
(phase correlation on the picture) changes from one pair of frames to the next, in px on the 1024 movie frame. A
still target or a steady pan scores 0.

| movie | before median / p90 | after median / p90 | |
|---|---|---|---|
| Titan 133TI CLOUD002 | 20.9 / 40.2 | 1.8 / 6.8 | titan133-cloud002.webp |
| Daphnis 09 ring movie (bench) | 9.3 / 15.0 | 0.5 / 0.9 | daphnis09-movie.webp |
| Methone 166ME | 0 / 11.9 | 0 / 1.9 | |
| Enceladus 221EN | 0 / 6.6 | 0 / 1.9 | enceladus221.webp |
| Pan 17 (bench) | 0 / 4.2 | 0 / 0.4 | pan17-movie.webp |
| Enceladus plume 161EN | 0 / 3.4 | 0 / 1.0 | |
| Jupiter rotation movie (bench) | 0.05 / 1.8 | 0.05 / 0.25 | jupiter-rmov-movie.webp |
| Tethys 239TE | 0 / 1.2 | 0 / 0.3 | |
| Telesto, Phoebe (bench) | p90 0.8, 0.9 | p90 0.4, 0.3 | |

Left as they are, because the chain links fewer than 80% of their frames: rings 2004 HIPHLFMOV001 (still
shakes about 9 px; rings2004-unchanged.webp), Saturn 2005 3X3MOVIEA002, Rhea's mutual event 128RH, Helene 149HE,
Enceladus 138EN. With a 50% bar, Enceladus 138EN improved (p90 11.1 to 7.7 px) but Helene got worse (3.2 to 4.4 px),
so the bar stays at 80%.
