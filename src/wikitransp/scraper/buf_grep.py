from __future__ import annotations

from io import SEEK_END, StringIO
from pathlib import Path
from typing import Iterator, TextIO

__all__ = ["grep_backwards"]


def grep_backwards(
    fh: TextIO,
    match_substr: str,
    line_ending: str = "\n",
    strip_eol: bool = False,
    step: int = 10,
) -> Iterator[str]:
    """
    Helper for scanning a file line by line from the end, imitating the behaviour of
    the Unix command line tools ``grep`` (when passed ``match_substr``) or ``tac`` (when
    ``match_substr`` is the empty string ``""``, i.e. matching all lines).

    Args:
      fh            : The file handle to read from
      match_substr  : Substring to match at. If given as the empty string, gives a
                      reverse line iterator rather than a reverse matching line iterator.
      line_ending   : The line ending to split lines on (default: "\n" newline)
      strip_eol     : Whether to strip (default: ``True``) or keep (``False``) line
                      endings off the end of the strings returned by the iterator.
      step          : Number of characters to load into chunk buffer (i.e. chunk size)
    """
    # Store the end of file (EOF) position as we are advancing backwards from there
    file_end_pos = fh.seek(0, SEEK_END)  # cursor has moved to EOF
    # Keep a reversed string line buffer as we are writing right-to-left
    revlinebuf = StringIO()
    # Keep a [left-to-right] string buffer as we read left-to-right, one chunk at a time
    chunk_buf = StringIO()
    # Initialise 'last chunk start' at position after the EOF (unreachable by ``read``)
    last_chunk_start = file_end_pos + 1
    line_offset = 0  # relative to SEEK_END
    has_EOF_newline = False  # may change upon finding first newline
    # In the worst case, seek all the way back to the start (position 0)
    while last_chunk_start > 0:
        # Ensure that read(size=step) will read at least 1 character
        # e.g. when step=4, last_chunk_start=3, reduce step to 3 --> chunk=[0,1,2]
        if step > last_chunk_start:
            step = last_chunk_start
        chunk_start = last_chunk_start - step
        fh.seek(chunk_start)
        # Read in the chunk for the current step (possibly after pre-existing chunks)
        chunk_buf.write(fh.read(step))
        while chunk := chunk_buf.getvalue():
            # Keep reading intra-chunk lines RTL, leaving any leftovers in revlinebuf
            lhs, EOL_match, rhs = chunk.rpartition(line_ending)
            if EOL_match:
                if line_offset == 0:
                    has_EOF_newline = rhs == ""
                # Reverse the right-hand-side of the rightmost line_ending and
                # insert it after anything already in the reversed line buffer
                if rhs:
                    # Only bother writing rhs to line buffer if there's anything in it
                    revlinebuf.write(rhs[::-1])
                # Un-reverse the line buffer --> full line after the line_ending match
                completed_line = revlinebuf.getvalue()[::-1]  # (may be empty string)
                # Clear the reversed line buffer
                revlinebuf.seek(0)
                revlinebuf.truncate()
                # `grep` if line matches (or behaves like `tac` if match_substr == "")
                if line_offset == 0:
                    if not has_EOF_newline and match_substr in completed_line:
                        # The 0'th line from the end (by definition) cannot get an EOL
                        yield completed_line
                elif match_substr in (completed_line + line_ending):
                    if not strip_eol:
                        completed_line += line_ending
                    yield completed_line
                line_offset += 1
            else:
                # If line_ending not found in chunk then add entire [remaining] chunk,
                # in reverse, onto the reversed line buffer, before chunk_buf is cleared
                revlinebuf.write(chunk_buf.getvalue()[::-1])
            # The LHS of the rightmost line_ending (if any) may contain another line
            # ending so truncate the chunk to that and re-iterate (else clear chunk_buf)
            chunk_buf.seek(len(lhs))
            chunk_buf.truncate()
        last_chunk_start = chunk_start
    if completed_line := revlinebuf.getvalue()[::-1]:
        # Iteration has reached the line at start of file, left over in the line buffer
        if line_offset == 0 and not has_EOF_newline and match_substr in completed_line:
            # The 0'th line from the end (by definition) cannot get an EOL
            yield completed_line
        elif match_substr in (
            completed_line + (line_ending if line_offset > 1 or has_EOF_newline else "")
        ):
            if line_offset == 1:
                if has_EOF_newline and not strip_eol:
                    completed_line += line_ending
            elif not strip_eol:
                completed_line += line_ending
            yield completed_line
    else:
        raise StopIteration


def rudimentary_grep_test():
    # Write lines counting to 100 saying 'Hi 0', 'Hi 9', ... give no. 27 a double newline
    str_list = [f"Hi {i}\n" if i != 27 else f"Hi {i}\n\n" for i in range(0, 100, 9)]
    str_out = "".join(str_list)
    example_file = Path("example.txt")
    no_eof_nl_file = Path("no_eof_nl.txt")  # no end of file newline
    double_eof_nl_file = Path("double_eof_nl.txt")  # double end of file newline

    with open(example_file, "w") as f_out:
        f_out.write(str_out)

    with open(no_eof_nl_file, "w") as f_out:
        f_out.write(str_out.rstrip("\n"))

    with open(double_eof_nl_file, "w") as f_out:
        f_out.write(str_out + "\n")

    file_list = [example_file, no_eof_nl_file, double_eof_nl_file]
    labels = [
        "EOF_NL    ",
        "NO_EOF_NL ",
        "DBL_EOF_NL",
    ]

    print("------------------------------------------------------------")
    print()
    print(f"match_substr = ''")
    for label, each_file in zip(labels, file_list):
        with open(each_file, "r") as fh:
            lines_rev_from_iterator = list(grep_backwards(fh=fh, match_substr=""))

        with open(each_file, "r") as fh:
            lines_rev_from_readline = list(reversed(fh.readlines()))

        print(label, f"{lines_rev_from_iterator == lines_rev_from_readline=}")
    print()

    for label, each_file in zip(labels, file_list):
        with open(each_file, "r") as fh:
            reverse_iterator = grep_backwards(fh=fh, match_substr="")
            first_match = next(reverse_iterator)
        print(label, f"{first_match=}")
    print()

    for label, each_file in zip(labels, file_list):
        with open(each_file, "r") as fh:
            all_matches = list(grep_backwards(fh=fh, match_substr=""))
        print(label, f"{all_matches=}")
    print()
    print()
    print("------------------------------------------------------------")
    print()
    print(f"match_substr = 'Hi 9'")

    for label, each_file in zip(labels, file_list):
        with open(each_file, "r") as fh:
            reverse_iterator = grep_backwards(fh=fh, match_substr="Hi 9")
            first_match = next(reverse_iterator)
        print(label, f"{first_match=}")
    print()

    for label, each_file in zip(labels, file_list):
        with open(each_file, "r") as fh:
            all_matches = list(grep_backwards(fh=fh, match_substr="Hi 9"))
        print(label, f"{all_matches=}")
    print()
    print("------------------------------------------------------------")
    print()
    print(f"match_substr = '\\n'")

    for len_flag in (True, False):
        for label, each_file in zip(labels, file_list):
            with open(each_file, "r") as fh:
                lines_rev_from_iterator = list(grep_backwards(fh=fh, match_substr="\n"))
            if len_flag:
                print(label, f"{len(lines_rev_from_iterator)=}")
            else:
                print(label, f"{lines_rev_from_iterator=}")
        print()

    for label, each_file in zip(labels, file_list):
        with open(each_file, "r") as fh:
            reverse_iterator = grep_backwards(fh=fh, match_substr="\n")
            first_match = next(reverse_iterator)
        print(label, f"{first_match=}")
    print()

    for label, each_file in zip(labels, file_list):
        with open(each_file, "r") as fh:
            all_matches = list(grep_backwards(fh=fh, match_substr="\n"))
        print(label, f"{all_matches=}")
    print()
    print("------------------------------------------------------------")
