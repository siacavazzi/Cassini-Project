// Moments the sessions open (times UTC to the second, as CLAUDE.md's links take them). The harness takes the first one
// inside the cache's slices (h.moment), so a sampler or rehearsal cache plays a moment it holds.
export const PLAY = [
  { t: "2006-09-15T14:28:00", label: "In Saturn's Shadow" },
  { t: "2013-07-19T22:23:19", label: "The Day the Earth Smiled" },
  { t: "2010-11-30T07:25:10", label: "The plumes of Enceladus" },
  { t: "2004-06-11T19:00:00", label: "Phoebe flyby" },
  { t: "2017-09-15T10:31:00", label: "Grand Finale" }
];
// a movie pass and a mosaic movie (laps over the north pole, 2017-04-26)
export const MOVIE = [
  { t: "2017-04-26T01:17:00", label: "north polar laps (mosaic movie)" },
  { t: "2005-02-17T05:46:09", label: "Enceladus flyby" },
  ...PLAY
];
// mosaics and colour pictures for full view and the lens
export const STILL = [
  { t: "2013-07-19T22:23:19", label: "The Day the Earth Smiled (mosaic)" },
  { t: "2005-02-17T05:46:09", label: "Enceladus (colour)" },
  ...PLAY
];
