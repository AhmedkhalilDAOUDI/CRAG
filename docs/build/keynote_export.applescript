on run argv
	set src to POSIX file (item 1 of argv)
	set dst to POSIX file (item 2 of argv)
	tell application "Keynote"
		activate
		open src
		set waited to 0
		repeat while (count of documents) = 0 and waited < 120
			delay 1
			set waited to waited + 1
		end repeat
		set d to front document
		export d to dst as PDF
		close d saving no
	end tell
end run
