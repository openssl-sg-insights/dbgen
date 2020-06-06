import readline
from functools import reduce
from os import system
from typing import TYPE_CHECKING
from typing import List as L
from typing import Optional as Opt
from typing import Any
from typing import Callable as C
from typing import Set as S
from typing import Dict as D
from typing import Tuple as T

if TYPE_CHECKING:
    from ..core.gen import Gen


def interact_gen(
    objs, gen: "Gen", input_rows: L[dict], max_rows: int = 200
) -> T[L[D[str, dict]], L[D[str, L[dict]]]]:
    """
    Allows a CLI for interacting with a generator given a set of input rows

    Args:
        gen (Gen): generator to interact with
        input_rows (L[dict]): list of input rows that simulate the query input

    Raises:
        ImportError: if prettytable, pprint and readline not installed (didn't
        want to require these in the requirements.txt just for this function)

    Returns:
        L[dict]: output of the generator
    """
    # Attempt to import necessary functions for formmatting
    try:
        from pprint import pprint
        from prettytable import PrettyTable  # type: ignore
    except ImportError:
        raise ImportError("Need pprint and prettytable for interact mode")

    # Initialize output list and valid responses for the outer question
    post_pyblocks: L[dict] = []
    action_dicts: L[dict] = []
    valid_responses = ("s", "c", "q", "m")
    # Initialize the response to user input and formatting delimiter func
    answer: Opt[str] = ""
    delimiter = lambda: print(
        "#----------------------------------------------------------------------------"
    )
    # Pretty table for displaying input row data
    x = PrettyTable(field_names=list(input_rows[0].keys()))

    while len(input_rows) > 0 and answer != "q":
        print_len = 200
        next_row = dict(input_rows.pop(0))
        next_row_str = lambda x: (
            str(next_row)[:x] + "..." if len(str(next_row)) > x else dict(next_row)
        )
        system("clear")
        print("Next Row:")
        x.add_row(next_row.values())
        print(x)
        answer = None
        while answer not in ("c", "s",):
            if answer == "m":
                print_len += 200
                pprint(next_row_str(print_len))
            elif answer not in valid_responses and answer is not None:
                delimiter()
                print("Invalid response, please select s/c/q/m")
                delimiter()
            else:
                delimiter()
            answer = input(
                "Continue(c), quit (q), skip (s), or expand current row(m)?\n"
            ).lower()
            if answer == "q":
                print("Quitting...")
                return post_pyblocks, action_dicts
        # Skip the row and clear the pretty table
        if answer == "s":
            x.clear_rows()
            continue
        delimiter()
        print("Processing Row...")
        list_of_processed_namespaces, curr_action_dicts = gen.test(
            objs, [next_row], verbose=True
        )
        curr_output = list_of_processed_namespaces[0]
        curr_action_dict = curr_action_dicts[0]
        system("clear")
        print("Next Row:")
        print(x)

        completer = get_completer(list(curr_output.keys()))
        readline.parse_and_bind("tab: complete")
        readline.set_completer(completer)
        display = ""
        delimiter()
        while display != "q":
            print("PyBlock Names:")
            for key in curr_output.keys():
                print("\t- " + key)
            delimiter()
            display = input(
                "What pyblock to display? (tab to see options/q to quit)\n"
            ).lower()
            if display in curr_output:
                delimiter()
                if display == "query":
                    print("Query Row:")
                else:
                    print(f"Function Name: {display}")
                print(f"Output:")
                try:
                    pprint(curr_output[display])
                except KeyboardInterrupt:
                    pass
                delimiter()
                while True:
                    if input("Press enter to continue\n") == "":
                        system("clear")
                        break
            elif display == "":
                system("clear")
                continue
            else:
                print("PyBlock Names:\n")
                pprint(list(curr_output.keys()))
                delimiter()
                print(f"Key not found in processed dict: {display}")
                delimiter()

        completer = get_completer(list(curr_action_dict.keys()))
        readline.set_completer(completer)
        display = ""
        while display != "q":
            print("Action Names:")
            for key in curr_action_dict.keys():
                print("\t- " + key + f" ({len(curr_action_dict[key])} rows)")

            delimiter()
            display = input(
                "What action to display? (tab to see options/q to quit)\n"
            ).lower()
            if display in curr_action_dict:
                delimiter()
                print(f"Table Name: {display}")
                print(f"Output:")
                try:
                    rows = curr_action_dict[display]
                    if rows:
                        all_keys: S[str] = reduce(
                            lambda prev, next: prev.union(set(next.keys())), rows, set()
                        )
                        table = PrettyTable(field_names=list(all_keys))
                        [
                            table.add_row(list(row.get(key) for key in all_keys))
                            for row in curr_action_dict[display][:max_rows]
                        ]
                        print(table)
                    else:
                        print("No rows to be updated or inserted")
                except KeyboardInterrupt:
                    pass
                delimiter()
                while True:
                    if input("Press enter to continue\n") == "":
                        system("clear")
                        break
            elif display == "":
                system("clear")
                continue
            else:
                delimiter()
                print(f"Key not found in Action Dict: {display}")
                delimiter()

        post_pyblocks.append(curr_output)
        action_dicts.append(curr_action_dict)
        x.clear_rows()

    print("No more rows left")
    return post_pyblocks, action_dicts


def get_completer(cmds: L[Any]) -> C[[str, int], Any]:
    def completer(text, state):
        options = [i for i in cmds if i.startswith(text)]
        if state < len(options):
            return options[state]
        else:
            return None

    return completer