# rz-titan13-movie2 (185TI, CB3+MT1 approximate colour): the warm band inside the limb

`limb_4x.jpg`: 1:1 limb crops, 4x nearest, base (91f0bdb2) left and fix (add88dfa) right, for frames 000, 010 and 023, with the mean R/G and B/G 8 to 24 px inside the limb (rows 470 to 530).

The band is in base too. Its R/G 8 to 24 px inside the limb, over all 27 frames:

| | median | min | max | frames over 1.15 |
|---|---|---|---|---|
| base | 1.120 | 1.105 | 1.171 | 13 of 27 |
| fix | 1.160 | 1.093 | 1.172 | 24 of 27 |

On base the band comes and goes from frame to frame. Frame 000 is warm on base (R/G 1.17 to 1.20) and neutral on the fix (1.09), and frame 023 is the other way round.

This colour is approximate, a CB3/MT1 ratio. MT1 is a methane band, and its limb haze profile differs from CB3's over about 20 px, so placing the two channels exactly against each other shows that ratio as a warm band. On base it showed in only the frames whose channels happened to sit that way.

The fix registers the channels better: channel_registration goes from 1.03 to 0.36 px, with the largest 0.50 px. So the band is now steady through the movie instead of flickering on and off.

The tint itself comes from the approximate-colour mapping, not from pointing.
