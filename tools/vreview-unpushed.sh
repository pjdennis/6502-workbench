#!/bin/bash
# Review unpushed commits with navigation

# Hide cursor and restore on exit
tput civis
trap 'tput cnorm; printf "\e[0 q"' EXIT

commits=($(git log @{u}..HEAD --reverse --format=%H))
total=${#commits[@]}

if [ "$total" -eq 0 ]; then
    echo "No unpushed commits."
    exit 0
fi

i=0
while true; do
    commit="${commits[$i]}"
    num=$((i + 1))
    clear

    # Build context-aware navigation message
    msg="Commit $num of $total: (Enter to view"
    [ "$i" -gt 0 ] && msg="$msg, ↑ for previous"
    [ "$i" -lt $((total - 1)) ] && msg="$msg, ↓ for next"
    msg="$msg, q to quit)"

    echo "$msg"
    echo

    # Limit output to terminal height with proper line wrapping
    term_height=$(tput lines)
    term_width=$(tput cols)

    # Calculate how many lines the header uses (accounting for wrapping)
    header_len=${#msg}
    if [ "$header_len" -eq 0 ]; then
        header_lines=1
    else
        header_lines=$(( (header_len + term_width - 1) / term_width ))
    fi

    # Available lines = total height - header lines - blank line
    available_lines=$((term_height - header_lines - 2))

    lines_used=0
    truncated=false

    while IFS= read -r line; do
        # Calculate how many terminal lines this line will use
        line_len=${#line}
        if [ "$line_len" -eq 0 ]; then
            lines_for_this=1
        else
            lines_for_this=$(( (line_len + term_width - 1) / term_width ))
        fi

        new_total=$((lines_used + lines_for_this))

        # Reserve 1 line for potential [more...] indicator
        if [ "$new_total" -gt $((available_lines - 1)) ]; then
            truncated=true
            break
        fi

        echo "$line"
        lines_used=$new_total
    done < <(git log --format=fuller -1 "$commit")

    if [ "$truncated" = true ]; then
        echo "[more...]"
    fi

    read -rsn1 key
    # Handle arrow keys (escape sequences)
    if [ "$key" = $'\e' ]; then
        read -rsn2 key  # Read the rest of the escape sequence
    fi

    case "$key" in
        v|$'\n'|"")  # v, Enter, or empty
            #git show --color=always "$commit" | less -R
            git difftool -t vimdiff -y "$commit^!"
            if [ "$i" -lt $((total - 1)) ]; then
                ((i++))
            else
                # At the last commit, show end message
                while true; do
                    clear
                    echo "No more commits (↑ for previous, q to quit)"
                    read -rsn1 endkey
                    if [ "$endkey" = $'\e' ]; then
                        read -rsn2 endkey
                    fi
                    case "$endkey" in
                        p|"[A") break ;;  # p or up arrow (i already at last commit)
                        q) exit 0 ;;
                    esac
                done
            fi
            ;;
        p|"[A") [ "$i" -gt 0 ] && ((i--)) ;;  # p or up arrow
        n|"[B") [ "$i" -lt $((total - 1)) ] && ((i++)) ;;  # n or down arrow
        q) break ;;
    esac
done
