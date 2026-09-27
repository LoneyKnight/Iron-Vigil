extends Node3D
## A door between two rooms. Blocks the way until the player pushes it aside.
##
## The door is the slice's core verb, so it is built to answer three questions without words:
## where is it (a dark oak panel in a stone wall), can I pass (no, it is solid), and did it
## work (it visibly goes away). Black Room shipped a bespoke first-person door interaction and
## never told the player how to use it; the prompt on this one is not optional.

const Util := preload("res://scripts/game/prop_util.gd")

const WIDTH := 1.6
const HEIGHT := 2.6

var dir := 0
var cell := Vector2i.ZERO
var opened := false

var _panel: MeshInstance3D
var _body: StaticBody3D


func build(room_cell: Vector2i, p_dir: int, world_pos: Vector3) -> void:
	dir = p_dir
	cell = room_cell
	add_to_group("interactive")
	position = world_pos

	var horizontal := p_dir % 2 == 0        # the doorway runs along X when the door is in a Z wall
	var size := (Vector3(WIDTH, HEIGHT, 0.3) if horizontal
		else Vector3(0.3, HEIGHT, WIDTH))

	_panel = Util.box(self, size, Vector3(0, HEIGHT * 0.5, 0), Util.mat(Util.OAK, 0.85))
	var band := Util.mat(Util.IRON, 0.55)
	for y in [0.6, 1.7]:
		var band_size := (Vector3(WIDTH * 1.02, 0.12, 0.34) if horizontal
			else Vector3(0.34, 0.12, WIDTH * 1.02))
		Util.box(self, band_size, Vector3(0, y, 0), band)
	_body = Util.blocker(self, size, Vector3(0, HEIGHT * 0.5, 0))
	Util.sensor(self, 2.2)


func prompt() -> String:
	return "" if opened else "开门"


func interact(_run) -> void:
	if opened:
		return
	opened = true
	# Slide the panel into the floor and drop the collider. No animation art needed: the door
	# visibly going away is the whole message.
	var tw := create_tween()
	tw.tween_method(_slide, 0.0, 1.0, 0.32)
	tw.tween_callback(func(): _body.queue_free())


func _slide(t: float) -> void:
	if _panel:
		_panel.position.y = HEIGHT * 0.5 - t * (HEIGHT + 0.2)
