/** Shared geometry constants. Any change here must be mirrored in apps/api/app/solver/constants.py. */
export const GRID = 0.1;               // m, validation grid
export const EPS = 1e-6;
export const DOOR_CLEARANCE = 0.9;     // m in front of a door
export const ACCESS_EDGE = 0.75;       // m free band for beds/desks/wardrobes/dressers
export const ACCESS_FREE_RATIO = 0.7;  // fraction of the band that must be free for the edge to count
export const WINDOW_BAND = 0.6;        // m depth of the window keep-clear band
export const CORRIDOR_CELLS = 2;       // erosion radius (cells) for a "comfortable" 0.5 m path
export const M2_TO_SQFT = 10.7639;
