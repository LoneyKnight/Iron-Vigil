extends Node
## Entry point. Registers the input map in code so the project has no hidden project.godot
## input state to drift out of sync with the game.

const INPUTS := {
	"move_up": [KEY_W, KEY_UP],
	"move_down": [KEY_S, KEY_DOWN],
	"move_left": [KEY_A, KEY_LEFT],
	"move_right": [KEY_D, KEY_RIGHT],
	# Running is a decision, not a convenience: it nearly doubles the speed and more than
	# quadruples the noise, which is the trade the whole sound system is built around.
	"run": [KEY_SHIFT],
}


func _ready() -> void:
	_setup_inputs()
	var scene: PackedScene = load("res://scenes/main.tscn")
	if scene == null:
		push_error("boot: res://scenes/main.tscn failed to load")
		return
	add_child(scene.instantiate())
	# Verification entry points. Kept here so the game and its tests start from the same scene
	# and the same input map — a test that builds its own world tests its own world.
	var args := OS.get_cmdline_user_args()
	if "--diag" in args:
		add_child(load("res://tests/diag.gd").new())
	elif "--shot" in args:
		add_child(load("res://tests/shot.gd").new())


func _setup_inputs() -> void:
	for action in INPUTS:
		if not InputMap.has_action(action):
			InputMap.add_action(action)
		for key in INPUTS[action]:
			var ev := InputEventKey.new()
			ev.physical_keycode = key
			InputMap.action_add_event(action, ev)
