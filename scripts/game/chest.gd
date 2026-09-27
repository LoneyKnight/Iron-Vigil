extends Node3D
## A chest. One item inside, and the item is visible from a distance if it matters.
##
## The glow on a relic chest is a deliberate concession: the loop is "find two relics, carry
## them to the altar", and if the player cannot tell a quest chest from a coin chest until
## after they have walked to it, the search stops being a choice and becomes a chore.

const Util := preload("res://scripts/game/prop_util.gd")

var loot := "gold"
var taken := false

var _lid: MeshInstance3D


func build(at: Vector3, p_loot: String) -> void:
	loot = p_loot
	add_to_group("interactive")
	position = at
	var body_mat := Util.mat(Util.OAK, 0.85)
	Util.box(self, Vector3(1.0, 0.62, 0.66), Vector3(0, 0.31, 0), body_mat)
	Util.box(self, Vector3(0.12, 0.64, 0.7), Vector3(0, 0.32, 0), Util.mat(Util.IRON, 0.55))
	_lid = Util.box(self, Vector3(1.04, 0.14, 0.7), Vector3(0, 0.68, 0), body_mat)
	if is_relic():
		Util.glow(self, Vector3(0, 0.8, 0), 2.2, 3.0)
	Util.sensor(self, 2.0)


func is_relic() -> bool:
	return loot.begins_with("relic_")


func prompt() -> String:
	if taken:
		return ""
	return "搜刮 · 圣物" if is_relic() else "搜刮"


func interact(run) -> void:
	if taken:
		return
	taken = true
	# Rummaging a chest is loud — louder than a footstep, quieter than a door — so searching
	# near something that is listening is a risk the player takes knowingly.
	Sound.play("chest_open", global_position, 4.0)
	run.collect(loot, global_position)
	var tw := create_tween()
	tw.tween_property(_lid, "rotation:x", -1.1, 0.22)
	tw.parallel().tween_property(_lid, "position:y", 0.8, 0.22)
