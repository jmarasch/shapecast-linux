#!/usr/bin/env bash
set -euo pipefail
runtime_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
original_args=("$@")
python_flags=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -s|-E|-B|-I|-O|-OO|-u|-q|-P|-S|-b|-bb|-v|-vv)
            python_flags+=("$1"); shift ;;
        -X|-W)
            [[ $# -ge 2 ]] || exec @PYTHON@ "${original_args[@]}"
            python_flags+=("$1" "$2"); shift 2 ;;
        -X?*|-W?*)
            python_flags+=("$1"); shift ;;
        -*)
            exec @PYTHON@ "${original_args[@]}" ;;
        *) break ;;
    esac
done
if [[ $# -eq 0 ]]; then
    exec @PYTHON@ "${original_args[@]}"
fi
exec @PYTHON@ "${python_flags[@]}" @HOST@ "$@"
