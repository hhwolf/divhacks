// Pure projection of a RoomPlan `CapturedRoom` into our skeleton JSON (packages/contracts/schemas/skeleton.schema.json)
// plus `objects` seeded for the Current Room layout. No UIKit, no session state — easy to reason about.
//
// Coordinate convention (documented in DECISIONS.md by the lead):
//   * RoomPlan is right-handed with Y up. Looking straight down at the floor with +X to the right, +Z points toward
//     the viewer (bottom of a plan). That is exactly our schema's frame, so ours.x = RoomPlan.x and ours.z = RoomPlan.z
//     with NO mirroring. Mirroring would flip handedness and put every door on the wrong side of its wall.
//   * Walls are chained end-to-end into one loop, corners are snapped to the intersection of neighbouring wall lines,
//     and the loop is reversed if its shoelace area in (x, z) is negative so that it winds clockwise on screen
//     (0,0) -> (L,0) -> (L,W) -> (0,W), matching fixtures/rooms/sample-nyc-bedroom.json.
//   * The origin is re-based so the min corner of the wall loop is (0, 0); heights are relative to the lowest wall base.
//   * Item rotation: the web editor applies three.js `rotation=[0, r, 0]`, i.e. local +X points at (cos r, -sin r) in
//     (x, z). RoomPlan shares that handedness, so yaw = atan2(-m02, m00) of the object's transform, quantised to 90°.
//   * Opening `offset` is the distance from the wall's (x1, z1) to the opening's START edge (see openingSpan in
//     packages/geometry/src/skeleton.ts), so offset = projection(center) - width / 2.

import Foundation
import simd

#if canImport(RoomPlan)
import RoomPlan

@available(iOS 16.0, *)
enum SkeletonExporter {
  // MARK: - Public entry point

  static func export(_ room: CapturedRoom) -> [String: Any] {
    var walls = room.walls.compactMap(Seg.init(wall:))
    guard walls.count >= 3 else {
      var out = emptyExport()
      out["meta"] = ["source": "roomplan", "reason": "fewer than 3 walls captured", "wallCount": walls.count]
      return out
    }

    walls = chain(walls)
    snapCorners(&walls)
    if signedArea(walls) < 0 { walls = walls.reversed().map { $0.flipped() } }

    let minX = walls.map { min($0.a.x, $0.b.x) }.min() ?? 0
    let minZ = walls.map { min($0.a.y, $0.b.y) }.min() ?? 0
    let maxX = walls.map { max($0.a.x, $0.b.x) }.max() ?? 0
    let maxZ = walls.map { max($0.a.y, $0.b.y) }.max() ?? 0
    let floorY = Double(walls.map { $0.bottomY }.min() ?? 0)
    let origin = SIMD2<Double>(minX, minZ)
    for i in walls.indices { walls[i].a -= origin; walls[i].b -= origin }

    let wallsJSON: [[String: Any]] = walls.map {
      ["x1": r3($0.a.x), "z1": r3($0.a.y), "x2": r3($0.b.x), "z2": r3($0.b.y), "height": r3(clamp($0.height, 1.5, 6))]
    }

    var doors: [[String: Any]] = []
    for d in room.doors {
      guard let o = Opening(surface: d, walls: walls, origin: origin, floorY: floorY) else { continue }
      doors.append([
        "wall": o.wall, "offset": r3(o.offset), "width": r3(clamp(o.width, 0.5, 2.5)),
        "height": r3(clamp(o.height, 1.5, 3.0)), "swing": "in", "hinge": "left",
      ])
    }

    var windows: [[String: Any]] = []
    for w in room.windows {
      guard let o = Opening(surface: w, walls: walls, origin: origin, floorY: floorY), o.width >= 0.3, o.height >= 0.3 else { continue }
      windows.append([
        "wall": o.wall, "offset": r3(o.offset), "width": r3(o.width),
        "sillHeight": r3(max(0, o.sill)), "height": r3(o.height),
      ])
    }

    let floorPolygon: [[Double]] = walls.map { [r3($0.a.x), r3($0.a.y)] }
    let dimensions: [String: Any] = [
      "l": r3(maxX - minX), "w": r3(maxZ - minZ), "h": r3(clamp(walls.map { $0.height }.max() ?? 2.7, 1.5, 6)),
    ]

    let (objects, detected, skipped) = mapObjects(room.objects, origin: origin)

    return [
      "skeleton": [
        "walls": wallsJSON, "doors": doors, "windows": windows, "floorPolygon": floorPolygon, "dimensions": dimensions,
      ] as [String: Any],
      "objects": objects,
      "meta": [
        "source": "roomplan",
        "convention": "x=RoomPlan.x, z=RoomPlan.z (no mirror), re-based to min corner, clockwise on screen",
        "wallCount": walls.count, "doorCount": doors.count, "windowCount": windows.count,
        "detected": detected, "skipped": skipped,
      ] as [String: Any],
    ]
  }

  static func emptyExport() -> [String: Any] {
    return [
      "skeleton": [
        "walls": [] as [[String: Any]], "doors": [] as [[String: Any]], "windows": [] as [[String: Any]],
        "floorPolygon": [] as [[Double]], "dimensions": ["l": 0.0, "w": 0.0, "h": 0.0],
      ] as [String: Any],
      "objects": [] as [[String: Any]],
    ]
  }

  // MARK: - Walls

  struct Seg {
    var a: SIMD2<Double>
    var b: SIMD2<Double>
    var height: Double
    var bottomY: Double
    let id: UUID

    /// Projects a wall surface to the floor plane: centre +- dims.x/2 along the wall's local X axis.
    init?(wall: CapturedRoom.Surface) {
      let m = wall.transform
      let c = SIMD2<Double>(Double(m.columns.3.x), Double(m.columns.3.z))
      var dir = SIMD2<Double>(Double(m.columns.0.x), Double(m.columns.0.z))
      let len = simd_length(dir)
      guard len > 1e-6, wall.dimensions.x > 0.2 else { return nil } // ignore degenerate / noise slivers
      dir /= len
      let half = Double(wall.dimensions.x) / 2
      a = c - dir * half
      b = c + dir * half
      height = Double(wall.dimensions.y)
      bottomY = Double(m.columns.3.y) - height / 2
      id = wall.identifier
    }

    func flipped() -> Seg { var s = self; s.a = b; s.b = a; return s }
    var dir: SIMD2<Double> { let d = b - a; let l = simd_length(d); return l > 1e-9 ? d / l : SIMD2(1, 0) }
    var length: Double { simd_length(b - a) }
  }

  /// Greedy nearest-endpoint chaining so walls[i].b meets walls[i+1].a. Handles L-shaped rooms; the corner snap
  /// below closes the small gaps RoomPlan leaves between neighbouring walls.
  static func chain(_ input: [Seg]) -> [Seg] {
    var remaining = input
    var ordered = [remaining.removeFirst()]
    while !remaining.isEmpty {
      let end = ordered[ordered.count - 1].b
      var bestIdx = 0, bestDist = Double.infinity, flip = false
      for (i, s) in remaining.enumerated() {
        let da = simd_distance(end, s.a), db = simd_distance(end, s.b)
        if da < bestDist { bestDist = da; bestIdx = i; flip = false }
        if db < bestDist { bestDist = db; bestIdx = i; flip = true }
      }
      let next = remaining.remove(at: bestIdx)
      ordered.append(flip ? next.flipped() : next)
    }
    return ordered
  }

  /// Replaces each shared corner with the intersection of the two wall lines (when they are not near-parallel and the
  /// intersection is close), otherwise with the midpoint of the two loose endpoints. Result: a closed polygon.
  static func snapCorners(_ walls: inout [Seg]) {
    let n = walls.count
    guard n >= 3 else { return }
    for i in 0..<n {
      let j = (i + 1) % n
      let p = walls[i].b, q = walls[j].a
      let d1 = walls[i].dir, d2 = walls[j].dir
      let cross = d1.x * d2.y - d1.y * d2.x
      var corner = (p + q) / 2
      if abs(cross) > 0.34 { // > ~20 degrees between the walls
        // Solve walls[i].a + t*d1 == walls[j].a + u*d2 for t.
        let r = walls[j].a - walls[i].a
        let t = (r.x * d2.y - r.y * d2.x) / cross
        let x = walls[i].a + d1 * t
        if simd_distance(x, p) < 0.75 && simd_distance(x, q) < 0.75 { corner = x }
      }
      walls[i].b = corner
      walls[j].a = corner
    }
  }

  static func signedArea(_ walls: [Seg]) -> Double {
    var s = 0.0
    for w in walls { s += w.a.x * w.b.y - w.b.x * w.a.y }
    return s / 2
  }

  // MARK: - Doors / windows

  struct Opening {
    let wall: Int
    let offset: Double
    let width: Double
    let height: Double
    let sill: Double

    init?(surface: CapturedRoom.Surface, walls: [Seg], origin: SIMD2<Double>, floorY: Double) {
      let m = surface.transform
      let c = SIMD2<Double>(Double(m.columns.3.x), Double(m.columns.3.z)) - origin
      var idx: Int? = nil
      if #available(iOS 17.0, *), let parent = surface.parentIdentifier {
        idx = walls.firstIndex { $0.id == parent }
      }
      if idx == nil { idx = SkeletonExporter.nearestWall(to: c, in: walls) }
      guard let wallIdx = idx, walls.indices.contains(wallIdx) else { return nil }
      let w = walls[wallIdx]
      width = Double(surface.dimensions.x)
      height = Double(surface.dimensions.y)
      let along = simd_dot(c - w.a, w.dir)
      offset = min(max(along - width / 2, 0), max(w.length - width, 0))
      sill = (Double(m.columns.3.y) - height / 2) - floorY
      wall = wallIdx
    }
  }

  static func nearestWall(to p: SIMD2<Double>, in walls: [Seg]) -> Int? {
    var best: (Int, Double)? = nil
    for (i, w) in walls.enumerated() {
      let ab = w.b - w.a
      let t = min(max(simd_dot(p - w.a, ab) / max(simd_dot(ab, ab), 1e-9), 0), 1)
      let d = simd_distance(p, w.a + ab * t)
      if best == nil || d < best!.1 { best = (i, d) }
    }
    return best?.0
  }

  // MARK: - Objects

  /// Category -> assets/furniture/manifest.json id. Returns layout items `{furnitureId, x, z, rotation, locked}` plus a
  /// debug list of everything detected (including skipped kitchen/bath fixtures).
  static func mapObjects(_ objects: [CapturedRoom.Object], origin: SIMD2<Double>) -> ([[String: Any]], [[String: Any]], [String]) {
    struct Det { let category: String; let key: String?; let x: Double; let z: Double; let w: Double; let d: Double; let h: Double; let yaw: Double }

    let centers = objects.map { o -> SIMD2<Double> in
      SIMD2(Double(o.transform.columns.3.x), Double(o.transform.columns.3.z)) - origin
    }
    let chairs = zip(objects, centers).filter { $0.0.category == .chair }.map { $0.1 }

    var dets: [Det] = []
    var skipped: [String] = []
    for (o, c) in zip(objects, centers) {
      let w = Double(o.dimensions.x), h = Double(o.dimensions.y), d = Double(o.dimensions.z)
      let m = o.transform
      let yawRad = atan2(-Double(m.columns.0.z), Double(m.columns.0.x))
      let yaw = (yawRad * 180 / .pi).truncatingRemainder(dividingBy: 360)
      let key: String?
      switch o.category {
      case .bed: key = min(w, d) >= 1.2 ? "bed_double" : "bed_single"
      case .table: key = chairs.contains { simd_distance($0, c) <= 1.0 } ? "desk" : "table"
      case .storage: key = h >= 1.5 ? "wardrobe" : "dresser"
      case .sofa: key = "sofa"
      case .chair: key = "chair"
      case .television: key = "tv_stand"
      default: key = nil // stove, refrigerator, sink, toilet, bathtub, washerDryer, oven, dishwasher, fireplace, stairs
      }
      let name = categoryName(o.category)
      if key == nil { skipped.append(name) }
      dets.append(Det(category: name, key: key, x: c.x, z: c.y, w: w, d: d, h: h, yaw: yaw))
    }

    let items: [[String: Any]] = dets.compactMap { det in
      guard let key = det.key else { return nil }
      return ["furnitureId": key, "x": r3(det.x), "z": r3(det.z), "rotation": quantise(det.yaw), "locked": false]
    }
    let detected: [[String: Any]] = dets.map {
      [
        "category": $0.category, "furnitureId": $0.key as Any? ?? NSNull(), "x": r3($0.x), "z": r3($0.z),
        "dims": ["w": r3($0.w), "d": r3($0.d), "h": r3($0.h)], "yaw": r3($0.yaw),
      ]
    }
    return (items, detected, skipped)
  }

  static func categoryName(_ c: CapturedRoom.Object.Category) -> String {
    switch c {
    case .storage: return "storage"
    case .refrigerator: return "refrigerator"
    case .stove: return "stove"
    case .bed: return "bed"
    case .sink: return "sink"
    case .washerDryer: return "washerDryer"
    case .toilet: return "toilet"
    case .bathtub: return "bathtub"
    case .oven: return "oven"
    case .dishwasher: return "dishwasher"
    case .table: return "table"
    case .sofa: return "sofa"
    case .chair: return "chair"
    case .fireplace: return "fireplace"
    case .television: return "television"
    case .stairs: return "stairs"
    @unknown default: return "unknown"
    }
  }

  // MARK: - Helpers

  /// Yaw in degrees -> 0 / 90 / 180 / 270.
  static func quantise(_ deg: Double) -> Int {
    guard deg.isFinite else { return 0 }
    let q = Int((deg / 90).rounded()) * 90
    return ((q % 360) + 360) % 360
  }

  static func clamp(_ v: Double, _ lo: Double, _ hi: Double) -> Double { min(max(v, lo), hi) }
  /// Round to mm; non-finite values (degenerate transforms) become 0 so the JSON stays valid for the API.
  static func r3(_ v: Double) -> Double { v.isFinite ? (v * 1000).rounded() / 1000 : 0 }
}
#endif
