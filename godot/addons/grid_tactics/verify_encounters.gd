extends SceneTree
## Command-line check: can the bot win every encounter in a folder?
##
##   godot --headless --path . --script res://addons/grid_tactics/verify_encounters.gd -- res://encounters
##
## Prints one line per EncounterData .tres and exits 1 if any was not won (or none were found),
## so CI fails when a stat tweak makes a fight unwinnable. A loss means "review this fight";
## see TacticsBot for what a result does and does not prove.


## _initialize() is a SceneTree script's entry point (like main() in other languages).
func _initialize() -> void:
	var args := OS.get_cmdline_user_args()          # everything after the `--`
	var dir: String = args[0] if not args.is_empty() else "res://encounters"
	var results := TacticsBot.verify_folder(dir)
	var failed := 0
	for path: String in results:
		var r: Dictionary = results[path]
		print("  %s  %s  rounds=%d survivors=%d hp_left=%d" % ["WIN " if r.won else "LOSS", path, r.rounds, r.survivors, r.hp_left])
		if not r.won:
			failed += 1
			print("::error title=%s::bot could not win this encounter (winner=%d)" % [path.get_file(), r.winner])
	print("\n%d encounters, %d not won" % [results.size(), failed])
	if results.is_empty():
		print("::error title=encounters::no EncounterData found under %s" % dir)
	quit(1 if failed > 0 or results.is_empty() else 0)
