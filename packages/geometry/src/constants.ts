/**
 * Shared geometry constants, read from packages/contracts/rules.json: the same file the API loads (app/solver/constants.py) and
 * serves at GET /validation/rules, so browser and server numbers cannot drift.
 */
import rules from '@arp/contracts/rules.json';

export const RULES_VERSION: number = rules.version;
export const GRID: number = rules.GRID_M;                         // m, validation grid
export const EPS = 1e-6;
export const DOOR_CLEARANCE: number = rules.DOOR_CLEAR_M;         // m in front of a door
export const ACCESS_EDGE: number = rules.ACCESS_EDGE_M;           // m free band along one long edge of beds/desks
export const STORAGE_FRONT: number = rules.STORAGE_FRONT_M;       // m free band in front of wardrobes/dressers/storage
export const ACCESS_FREE_RATIO: number = rules.ACCESS_FREE_RATIO; // fraction of a band that must be free for the edge to count
export const WINDOW_BAND: number = rules.WINDOW_BAND_M;           // m depth of the window keep-clear band
export const CORRIDOR_CELLS: number = rules.CORRIDOR_CELLS;       // erosion radius (cells) for a "comfortable" 0.5 m path
export const DEFAULT_YOGA_ZONE: [number, number] = [rules.DEFAULT_YOGA_ZONE_M[0], rules.DEFAULT_YOGA_ZONE_M[1]];
export const M2_TO_SQFT = 10.7639;
