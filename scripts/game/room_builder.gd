extends Node3D
## Builds the geometry for a chapter house: floors, walls with doorways, and the fixed
## props. One instance owns the whole level.
##
## Why the walls are decided by the LAYOUT and not by the room: two adjacent rooms share a
## wall, so a wall exists exactly where there is no neighbour. Building four walls per room
## and cutting holes in them produces doubled geometry and z-fighting at every seam.
##
## The cutaway from the framing work still applies, and it is per-room: the wall on the
## camera-facing side of a room is left low. That keeps the room readable from a fixed camera
## angle and is why the level is authored for one camera and never rotated.

const House := preload("res://scripts/game/chapter_house.gd")

const WALL_HEIGHT := 4.6
const WALL_T := 0.4
const PARAPET_H := 0.55
const TILE_PX := 85          # procedural tile canvas: one floor tile at the design density
const HALF_TILE_PX := 43

const INK := Color("16130f")
const STONE := Color("6a665c")
const STONE_DARK := Color("4a4741")
const IRON := Color("3a3a3e")

var house: House
var _floor_mats := {}          # theme -> material, so one material is not rebuilt per room
var _wall_mat: StandardMaterial3D


func build(p_house: House) -> void:
	house = p_house
	_wall_mat = _make_wall_material()
	for cell in house.rooms:
		_build_room(house.rooms[cell])


# ---------------------------------------------------------------------------------------
# materials: procedural, because a floor repeats hundreds of times and must be quiet
# ---------------------------------------------------------------------------------------

func _make_floor_material(theme: String) -> StandardMaterial3D:
	# Prefer a real tile if one exists for this floor material, fall back to the procedural
	# one otherwise. The fallback is not a stopgap to be removed later: it keeps the game
	# runnable while art is being generated, and it keeps a missing file from being a crash.
	var asset := "res://assets/tiles/floor_%s.png" % theme
	if not ResourceLoader.exists(asset):
		asset = "res://assets/tiles/floor_stone.png"
	var m := StandardMaterial3D.new()
	if ResourceLoader.exists(asset):
		m.albedo_texture = load(asset)
		# The tile is authored at 64 texels for 1 metre (tools/art/tiles.py). One UV repeat
		# per metre is therefore the whole scale relationship, and it is the reason the
		# density in style_spec.md §1 comes out right: 85 px per metre on screen.
		m.uv1_scale = Vector3(House.ROOM_M, House.ROOM_M, 1.0)
	else:
		m.albedo_texture = _procedural_floor()
		m.uv1_scale = Vector3(House.ROOM_M / 3.0, House.ROOM_M / 3.0, 1.0)
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS
	m.roughness = 0.95
	return m


func _make_wall_material() -> StandardMaterial3D:
	var asset := "res://assets/tiles/wall_stone.png"
	var m := StandardMaterial3D.new()
	if ResourceLoader.exists(asset):
		m.albedo_texture = load(asset)
		# 64 texels for 1 metre of wall face, the same relationship as the floor, so the density
		# in style_spec.md §1 holds on the walls too. It was briefly halved to make the masonry
		# quieter and that was a mistake: it also doubled the apparent size of every block, and
		# the coursing stopped matching the floor. If the walls read as too busy, the fix belongs
		# in the texture, not in the scale.
		m.uv1_scale = Vector3(1.0, WALL_HEIGHT, 1.0)
	else:
		m.albedo_texture = _procedural_wall()
		m.uv1_scale = Vector3(1.0, WALL_HEIGHT / 2.0, 1.0)
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS
	m.roughness = 0.9
	return m


## Procedural fallback: 3x3 tiles with the mortar seam on the tile border, so a 3x3
## arrangement reproduces seamlessly and one texture covers three metres.
func _procedural_floor() -> ImageTexture:
	var t := TILE_PX
	var size := t * 3
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	for y in size:
		for x in size:
			var tx := x % t
			var ty := y % t
			var n := float((x * 7 + y * 13 + (x / 8) * 5) % 9) / 9.0
			if tx == 0 or ty == 0:
				img.set_pixel(x, y, STONE_DARK.darkened(0.10 + n * 0.06))
			else:
				var v := STONE.darkened(0.02 + n * 0.07)
				if tx == t / 2 and ty > t / 2:
					v = v.darkened(0.16)
				img.set_pixel(x, y, v)
	return ImageTexture.create_from_image(img)


func _procedural_wall() -> ImageTexture:
	var course := HALF_TILE_PX
	var w := course * 2
	var h := course * 2
	var img := Image.create(w, h, false, Image.FORMAT_RGBA8)
	for y in h:
		for x in w:
			var row := y / course
			var offset := (row % 2) * (w / 4)
			var in_joint: bool = (y % course == 0) or ((x + offset) % w == 0)
			var n := float((x * 11 + y * 5 + row * 3) % 7) / 7.0
			var base := STONE.darkened(0.18)
			img.set_pixel(x, y, IRON.lerp(base, 0.62) if in_joint else base.darkened(n * 0.08))
	return ImageTexture.create_from_image(img)


# ---------------------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------------------

func _build_room(room: House.Room) -> void:
	var span := House.ROOM_M
	var c := room.centre()
	if not _floor_mats.has(room.theme):
		_floor_mats[room.theme] = _make_floor_material(room.theme)
	_slab(Vector3(span, 0.2, span), c + Vector3(0, -0.1, 0), _floor_mats[room.theme])

	var half := span * 0.5
	for dir in 4:
		var d: Vector2i = House.DIRS[dir]
		var at := c + Vector3(float(d.x) * half, 0.0, float(d.y) * half)
		var horizontal := dir % 2 == 0
		var length := span

		if room.linked.has(dir):
			# A doorway: two wall pieces with a gap the player walks through. The gap is
			# the same width on both sides of the shared wall because both rooms compute it
			# from House.DOOR_W.
			var gap := House.DOOR_W
			for side in [-1, 1]:
				var seg_len := (length - gap) * 0.5
				if seg_len <= 0.01:
					continue
				var off := (gap * 0.5 + seg_len * 0.5) * float(side)
				var pos := at
				if horizontal:
					pos += Vector3(0, 0, 0)  # gap runs along X
					_wall_piece(Vector3(seg_len, WALL_HEIGHT, WALL_T),
						c + Vector3(off, WALL_HEIGHT * 0.5, float(d.y) * half))
				else:
					_wall_piece(Vector3(WALL_T, WALL_HEIGHT, seg_len),
						c + Vector3(float(d.x) * half, WALL_HEIGHT * 0.5, off))
			# Lintel above the opening, so a doorway reads as architecture.
			var lintel_h := WALL_HEIGHT - 2.6
			if lintel_h > 0.1:
				var lsize := (Vector3(gap + 0.4, lintel_h, WALL_T) if horizontal
					else Vector3(WALL_T, lintel_h, gap + 0.4))
				_wall_piece(lsize, at + Vector3(0, WALL_HEIGHT - lintel_h * 0.5, 0))
			continue

		# No neighbour: a solid wall. The camera-facing side (+Z, dir 2) stays low so it
		# never stands between the camera and the room — the cutaway from style_spec §2.2.
		var h := PARAPET_H if dir == 2 else WALL_HEIGHT
		var size := (Vector3(length, h, WALL_T) if horizontal
			else Vector3(WALL_T, h, length))
		_wall_piece(size, at + Vector3(0, h * 0.5, 0))


func _slab(dim: Vector3, at: Vector3, mat: Material) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = dim
	var node := MeshInstance3D.new()
	node.mesh = mesh
	node.material_override = mat
	node.position = at
	add_child(node)
	return node


## A wall piece: a mesh, plus a collider when it is tall enough to stop the player. The
## parapet is deliberate waist-height geometry, so it gets a collider too — otherwise the
## player walks off the edge of every south-facing room.
func _wall_piece(dim: Vector3, at: Vector3) -> void:
	_slab(dim, at, _wall_mat)
	var body := StaticBody3D.new()
	var col := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = dim
	col.shape = shape
	body.add_child(col)
	body.position = at
	add_child(body)
