extends Node3D
## The altar: the end of the run. Wants the two relics, and says so when it does not have them.
##
## The refusal is the important part. An altar that silently does nothing when the player
## arrives without the relics teaches them that the altar is broken; one that names what is
## missing teaches them the rule in one sentence and no tutorial.

const Util := preload("res://scripts/game/prop_util.gd")

var done := false

var _glow: OmniLight3D


func build(at: Vector3) -> void:
	add_to_group("interactive")
	position = at
	var stone := Util.mat(Util.STONE, 0.95)
	Util.box(self, Vector3(2.0, 0.95, 1.0), Vector3(0, 0.48, 0), stone)
	Util.box(self, Vector3(2.3, 0.16, 1.25), Vector3(0, 1.02, 0), Util.mat(Util.STONE_DARK, 0.95))
	# A blood channel cut into the top: the one detail that makes it an altar and not a table.
	Util.box(self, Vector3(1.5, 0.06, 0.16), Vector3(0, 1.11, 0), Util.mat(Util.OXBLOOD, 0.7))
	for i in 5:
		Util.box(self, Vector3(0.1, 0.34, 0.1),
			Vector3(-0.8 + float(i) * 0.4, 1.27, -0.36), Util.mat(Color("d8cfae"), 0.9))
	_glow = Util.glow(self, Vector3(0, 1.7, 0), 0.0, 7.0)
	Util.sensor(self, 2.6)


func prompt() -> String:
	return "" if done else "举行仪式"


func interact(run) -> void:
	if done:
		return
	# Refuse out loud, and name what is missing. This is the entire tutorial for the win
	# condition and it costs one line.
	if not run.has_all_relics():
		Sound.play("altar_refuse", global_position, 2.0)
		run.say("圣物不全：还缺 %s" % run.missing_relics_text())
		return
	done = true
	# The run's resolution, and it should be audible from anywhere in the building: the rite
	# completing is the loudest and longest sound in the game, and it ends everything.
	Sound.play("altar_lit", global_position, 14.0)
	run.finish_rite(self)
	var tw := create_tween()
	tw.tween_property(_glow, "light_energy", 3.2, 0.7)
