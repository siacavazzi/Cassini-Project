# Lightning on Saturn: Moments and an enhanced view

Sam 2026-11-16: the lightning-search passes show no lightning on the site. Cassini's camera did catch flashes, on four
dates; Dyudina et al. 2013 (Icarus 226, Table A1, [open copy](https://authors.library.caltech.edu/records/y7mpy-9dw16))
lists every one. All their frames are in the archive. The flashes are in the data; the site's look hides them (night
side: white is set by the sunlit rings; day side: a flash is a few percent over bright clouds).

| file | what |
|---|---|
| `page-nov30-2038.jpg` | the page on the Nov 30 2009 Lightning Moment at 20:38 UTC: the Narrow-angle window as today (dark, nothing to see) and the new Lightning window on the same picture |
| `window-nov30-2046.jpg` | the Lightning window at 20:46, two flashes in the storm |
| `night-nov30.jpg`, `night-aug17.jpg` | crops: the site's picture today (top) and the same frame's I/F with a storm stretch (bottom), every frame of the flashes |
| `pass-2009-11-30.jpg`, `pass-2009-08-17.jpg` | every picture of the two night passes as the pre-build makes them, the paper's flashes ringed where SPICE puts them |
| `day-2011-02-26.jpg` | four day-side flashes in the Great White Spot: the frame plainly stretched, and its enhanced view (warm = brighter than the pictures 10 minutes before and after) |

Honest limits: on the day side only 4 of the 10 Feb 26 flashes clear the tint threshold (the other six are within
the noise of the differencing; the paper's own estimates are 1 to 4 billion J); about one other warm spot per picture
is a cloud that changed, which is why the published flashes are ringed. The Aug 17 frames were 12-bit originals
stored as 8-bit codes in the lean archive; their LUT step (about 17 DN at 1,340 DN) is below twice the shot noise and
the flashes come through. Made with web/frames/lightning.py on the M5 from the lean archive and the JAN05 kernels.
