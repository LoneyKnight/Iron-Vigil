extends RefCounted
## Generates a chapter house: a connected set of rooms on a grid, plus what is in them.
##
## Deliberately simple for the vertical slice — a random walk that grows a connected blob,
## then places contents by walking outward from the entrance so the relics are never in the
## first room the player sees. A real generator (hand-authored templates, themed floors,
## keys and locks) replaces this without the rest of the game noticing, as long as it
## produces the same three things: `rooms`, `entrance`, and `relic_rooms`.

const ROOM_M := 7.0          # a room is 7 x 7 metres; see style_spec.md §2.1
const ROOM_PITCH := 7.4      # room + wall thickness, so neighbours share a wall
const DOOR_W := 1.6

## Grid directions. Index is used everywhere as the door id, so the order matters:
## 0 = north (-Z), 1 = east (+X), 2 = south (+Z), 3 = west (-X).
const DIRS := [Vector2i(0, -1), Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0)]
const OPPOSITE := [2, 3, 0, 1]

var rooms := {}                 # Vector2i -> Room
var entrance := Vector2i.ZERO
var relic_rooms := []           # room ids holding a relic, in the order they were placed

var rng := RandomNumberGenerator.new()


class Room:
	var cell: Vector2i
	var doors := {}             # dir id -> true, where a doorway exists in this wall
	var linked := {}            # dir id -> Vector2i of the neighbour (door is openable)
	var opened := {}            # dir id -> true once the door has been pushed aside
	var chests := []            # Array[Dictionary]: {"at": Vector3, "loot": String, "taken": bool}
	var enemy_spawn := []       # Array[Vector3]
	var has_altar := false
	func _init(c: Vector2i) -> void:
		cell = c

	## World centre of the room on the floor plane.
	func centre() -> Vector3:
		return Vector3(float(cell.x) * ROOM_PITCH, 0.0, float(cell.y) * ROOM_PITCH)

	## World position of the doorway in `dir`.
	func door_position(dir: int) -> Vector3:
		var d: Vector2i = DIRS[dir]
		var half := ROOM_M * 0.5
		return centre() + Vector3(float(d.x) * half, 0.0, float(d.y) * half)


func generate(room_count: int = 8, seed_value: int = 0) -> void:
	rng.seed = seed_value if seed_value != 0 else randi()
	rooms.clear()
	relic_rooms.clear()

	# Grow a connected blob. Always connect the new room to the room it grew FROM, so the
	# result is connected by construction — the connectivity test afterwards is a check on
	# the code, not a fixup.
	var order: Array[Vector2i] = [Vector2i.ZERO]
	rooms[Vector2i.ZERO] = Room.new(Vector2i.ZERO)
	var guard := 0
	while rooms.size() < room_count and guard < 500:
		guard += 1
		var from: Vector2i = order[rng.randi_range(0, order.size() - 1)]
		var dir := rng.randi_range(0, 3)
		var to: Vector2i = from + DIRS[dir]
		if rooms.has(to):
			continue
		var nr := Room.new(to)
		nr.doors[OPPOSITE[dir]] = true
		rooms[from].doors[dir] = true
		rooms[from].linked[dir] = to
		nr.linked[OPPOSITE[dir]] = from
		rooms[to] = nr
		order.append(to)

	entrance = Vector2i.ZERO
	# Depth from the entrance, so content can be placed by distance rather than at random.
	var depth := _depths(entrance)
	var by_depth := order.duplicate()
	by_depth.sort_custom(func(a, b): return depth.get(a, 0) > depth.get(b, 0))

	# Two relics, in the farthest rooms. Putting them anywhere near the entrance makes the
	# loop 30 seconds long and the whole slice proves nothing.
	var relics := ["relic_dagger", "relic_tallow"]
	var placed := 0
	for cell in by_depth:
		if placed >= relics.size():
			break
		if cell == entrance:
			continue
		var room: Room = rooms[cell]
		room.chests.append({"at": _chest_spot(room, 0), "loot": relics[placed], "taken": false})
		relic_rooms.append(cell)
		placed += 1

	# The altar goes in a far room that is not holding a relic, so the player has to travel
	# back through the house to use them.
	for cell in by_depth:
		if cell == entrance or cell in relic_rooms:
			continue
		if depth.get(cell, 0) < 2:
			continue
		rooms[cell].has_altar = true
		rooms[cell].chests.append({"at": _chest_spot(rooms[cell], 1), "loot": "gold", "taken": false})
		break

	# Mundane chests and cultists spread over the rest.
	var mundane := ["gold", "gold", "bandage", "gold"]
	var mi := 0
	var cultists := 0
	for cell in order:
		if cell == entrance:
			continue
		var room: Room = rooms[cell]
		var filled := room.chests.size()
		if filled < 2 and mi < mundane.size():
			room.chests.append({"at": _chest_spot(room, filled), "loot": mundane[mi], "taken": false})
			mi += 1
		if cultists < 3 and depth.get(cell, 0) >= 1 and not room.has_altar:
			room.enemy_spawn.append(room.centre() + Vector3(1.2, 0.0, 1.0))
			cultists += 1


## Breadth-first depth from the entrance, used both for placement and for the connectivity
## assertion in tests.
func _depths(from: Vector2i) -> Dictionary:
	var d := {from: 0}
	var q: Array[Vector2i] = [from]
	while not q.is_empty():
		var cur: Vector2i = q.pop_front()
		for dir in rooms[cur].linked:
			var nb: Vector2i = rooms[cur].linked[dir]
			if not d.has(nb):
				d[nb] = int(d[cur]) + 1
				q.append(nb)
	return d


## True when every generated room is reachable from the entrance.
##
## NOT called `is_connected`: that name belongs to Object and overriding it is a compile
## error in Godot 4 ("the method overrides a method from native class"), which fails the
## whole script. A generated layout always claims to be connected; this is what checks it.
func all_rooms_reachable() -> bool:
	return _depths(entrance).size() == rooms.size()


## A chest position inside the room, offset per index so two chests do not overlap.
func _chest_spot(room: Room, index: int) -> Vector3:
	var spots := [Vector3(-2.0, 0.0, 1.6), Vector3(2.1, 0.0, -1.8), Vector3(0.0, 0.0, 2.2)]
	return room.centre() + spots[index % spots.size()]
