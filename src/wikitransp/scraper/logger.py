from __future__ import annotations

import logging
import time
from enum import Enum
from io import SEEK_END, StringIO
from logging.handlers import RotatingFileHandler
from pathlib import Path
from sys import stderr, stdout
from typing import Literal, Type, overload

from humanfriendly import format_timespan

from ..logs import logs_dir
from .buf_grep import grep_backwards

__all__ = ["Logger", "Log", "Event"]


class MaxLogFailureError(ValueError):
    def __init__(self, log: Logger):
        message = f"Hit maximum number of consecutive failures {log.fail_limit}"
        super().__init__(message)


class Log(Enum):
    """
    The different types of logged event, in order of execution (with any non-specific
    event types, which don't need to be ordered relative to the rest, afterwards).
    """

    Init = 0
    MatchResume = 1
    CheckPng = 2
    PrePngStream = 3
    PrePngStreamAsyncFetcher = 4
    PngStream = 5
    FetchIteration = 6
    PopulateChunks = 7
    DirectAlpha = 8
    ConfAlpha = 9
    WriteRow = 10
    ConfAlphaNeg = 11
    DirectAlphaNeg = 12
    PngSuccess = 13
    PngDone = 14
    UnclosedStreamException = 15
    RoutineException = 16
    BanURL = 17
    BanURLException = 18  # Deprecated
    URLException = 19
    GarbageCollect = 20
    AverageTime = 21
    EarlyHalt = 22
    HaltFinished = 23
    LogNotify = 24
    ResumePoint = 25
    BonVoyage = 26
    InternalLogException = 27  # Non-specific


class Logger:
    """
    A logger class for the scraping procedure (in :mod:`wikitransp.scraper.check_png`).
    Initially did not use the :mod:`logging` module so has both levels and verbosity
    controls (may adapt/remove at a later date).
    """

    DEFAULT_FILE_NAME: str = "wikitransp.log"

    def __init__(
        self,
        name: str = "",
        log_level: int = logging.DEBUG,
        console_level: int = logging.CRITICAL,
        simple: bool = True,
        which: list[Log] | None = None,
        internal: bool = False,
        line_ending: str = "\n",
        path: Path | None = None,
        n_logs: int = 10,
        term_headers: bool = False,
        fail_limit: int = 10,
        auto_resume: bool = False,  # Implementation mostly finished
    ):
        """
        Create a logger writing events level :obj:`logging.INFO` and above to STDERR,
        and level :obj:`logging.DEBUG` and above to ``path`` (defaulting to ``None``,
        resulting in the package-internal logs directory at :mod:`wikitransp.logs`).

        Args:
          name          : The name for the logger (recommended: pass ``__name__`` from
                          the calling module to show the path within your package).
                          Default: ``''`` (the empty string), giving the root logger.
          log_level     : Default log file level (default: :obj:`logging.DEBUG`)
          console_level : Default console log level (default: :obj:`logging.INFO`)
          sample        : Whether the run is for the sample
          simple        : Whether to print duration simply in logs or with the event
                          the duration is in comparison to
          which         : A list of :class:`~wikitransp.scraper.logger.Log` enums, or
                          ``None``, which is interpreted to mean all enums.
          line_ending   : The default line ending for logs (default: "\n"), overridable
                          per-entry using the `add` method's ``suffix`` argument.
          path          : The path to write the log to (rotated up to ``n_logs`` times).
          n_logs        : The maximum number of log backups to keep in rotation (total)
          term_headers  : Whether to show log headers in the console logs.
          fail_limit    : Consecutive failure count before raising MaxLogFailureError
        """
        self.name = name
        self.log_level = log_level
        self.console_level = console_level
        self.logs: dict[str, list[Event]] = {}
        self.LINE_ENDING = line_ending
        self.simple = simple
        self.path = path
        self.n_logs = n_logs
        self.fail_limit = fail_limit
        self.auto_resume = auto_resume
        self.consecutive_failures = 0
        self.prepare_logging(console_headers=term_headers)
        self.filter = [] if which is None else which
        self.add(Log.Init)

    @property
    def log_file(self) -> Path:
        """
        Path to the log output file
        """
        return logs_dir / self.DEFAULT_FILE_NAME if self.path is None else self.path

    def grep_backwards(
        in_file: Path,
        match_substr: str,
        chunk_size=10,
        max_count: int = 0,
    ) -> list[str]:
        """
        Helper for scanning a file line by line from the end (when inspecting log
        messages that come at the end of the logs).

        Args:
          in_file      : Path of the file to grep backwards in (will be opened and
                         closed within the method call)
          match_substr : Substring to match on a line. Regular expression not supported
          chunk_size   : How many characters to load into the buffer per read chunk.
                         Should be roughly around or above file's characters per line
          max_count    : How many matching lines to extract.
        """
        with open(in_log_file, "r") as f:
            match_it = grep_backwards(f, match_substr=match_substr, step=chunk_size)
            matched_lines = []
            if max_count > 0:
                for i in range(max_count):
                    try:
                        matched_lines.append(next(match_it))
                    except StopIteration:
                        break
            else:
                # No maximum, i.e. return any and all matches, i.e. exhaust iterator
                matched_lines.extend(list(match_it))
        return matched_lines

    def detect_resume_point(self, log_path: Path) -> None:
        # Grep from the end of the file backwards
        self.grep_backwards(in_log_file=log_path, match_substr="ResumePoint ⠶ ")

    def prepare_logging(
        self,
        console_headers: bool = False,
        log_format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
        date_format="%m-%d %H:%M",
    ):
        """
        Prepare the custom logger. Note: if :meth:`logging.basicConfig` has been called
        already, it'll override the call within this method.
        """
        log_pre_exists = self.log_file.exists()
        if self.auto_resume:
            self.detect_resume_point(self.log_file)

        # Do log rotation (handler not added to logger, just used to rollover if needed)
        rot_handler = RotatingFileHandler(
            filename=self.log_file,
            maxBytes=0,  # Will not write to file
            backupCount=self.n_logs,
        )
        if log_pre_exists:
            rot_handler.doRollover()

        # Set up logging to file
        logging.basicConfig(
            level=logging.DEBUG,  # Lowest named level: log all levels to file
            format=log_format,
            datefmt=date_format,
            filename=self.log_file,
            filemode="w",
        )

        # define a Handler which writes INFO messages or higher to the sys.stderr
        console = logging.StreamHandler()
        console.setLevel(self.console_level)
        # Simpler format for console (no date), no headers at all if `console_headers`
        console_format = "%(name)-12s: %(levelname)-8s " if console_headers else ""
        console_format += "%(message)s"
        formatter = logging.Formatter(console_format)
        # tell the handler to use this format
        console.setFormatter(formatter)
        # add the handler to the root logger
        logging.getLogger().addHandler(console)

        # Now, we can log to the root logger, or any other logger. First the root...
        # logging.getLogger(__name__).debug("Is this thing on?")

    @property
    def time_since_init(self) -> str:
        """
        Return a human-readable representation of the time since the Log.Init event.
        """
        log_init_event_t = Log.Init
        if self.has_event(which=log_init_event_t):
            init_event = self.get_prior_event(which=log_init_event_t)
            init_time = init_event.when
            elapsed_seconds = time.time() - init_time
            elapsed_time = format_timespan(elapsed_seconds)
        else:
            elapsed_time = "N/A"
        return elapsed_time

    @property
    def filter(self) -> list[Log]:
        return self._logged_types

    @filter.setter
    def filter(self, which: list[Log]) -> None:
        if which is not None and not all(isinstance(w, Log) for w in which):
            err_msg = (
                f"Invalid filter type: {which=}. Pass a list of Log enums or an empty "
                "list (which is interpreted as meaning log all event types)"
            )
            raise TypeError(err_msg)
        self._logged_types = which

    def is_in_filters(self, which: Log) -> bool:
        """
        Determine whether a type of logged event is in the
        :attr:`~wikitransp.scraper.logger.Logger.filter` list.
        """
        if self.filter is None:
            is_in = True
        else:
            is_in = (self.filter == [] or which in self.filter) and (
                isinstance(which, Log)  # Ensure it's in the Enum
            )
        return is_in

    def write_message(
        self,
        msg: str,
        level: int = logging.DEBUG,
        line_ending: str = "\n",
    ) -> None:
        """
        Write the message to the log handler(s) at the given level, using a custom line
        ending and splitting newlines into separate log lines (to avoid having a newline
        in a message 'spilling over' into an unprefixed and therefore making its
        provenance ambiguous if filtered: seems to be standard/best practice).
        """
        is_error = level == logging.ERROR
        log_msg = msg + line_ending  # N.B. ``msg`` may be multiline
        # Slice off a single newline if present at the end, so as to preserve
        # non-EOL newlines when splitting multi-line strings (but logged separately)
        log_lines = log_msg[: (-1 if log_msg.endswith("\n") else None)].split("\n")
        for log_line in log_lines:
            logging.getLogger(self.name).log(level=level, msg=log_line)

    def write_event(
        self,
        level: int,
        event: Event,
        only_msg: bool = False,
        prefix="",
        suffix: str = "\n",
    ) -> None:
        """
        Log the event's message to the appropriate handler(s).
        """
        msg = event.msg if only_msg else prefix + repr(event)
        self.write_message(
            msg=msg,
            level=level,
            line_ending=suffix,
        )

    def early_halt(self):
        """
        Indicate the elapsed time and where to find the full log when the program halts.
        """
        elapsed_t = self.time_since_init
        msg = f"Early halt after {elapsed_t}. For the full log see {self.log_file}"
        self.add(Log.EarlyHalt, msg=msg, prefix="\n    ", level=logging.CRITICAL)

    def suggest_resume(self):
        """
        Give a helpful suggestion of where to resume at in the event the user halts the
        program before it completes. Capitalise to emphasise whether it's at or after
        the URL in question.
        """
        if self.has_event(which=Log.CheckPng):
            resume_where = "AT"
            png_check_event_t, tsv_write_event_t = Log.CheckPng, Log.WriteRow
            last_checked_png = self.get_prior_event(which=png_check_event_t)
            last_url = last_checked_png.msg.split("@")[-1].strip()
            last_png_checked_time = last_checked_png.when
            if self.has_event(which=tsv_write_event_t):
                last_tsv_write = self.get_prior_event(which=tsv_write_event_t)
                last_tsv_write_time = last_tsv_write.when
                if last_tsv_write_time > last_png_checked_time:
                    # The last checked PNG was entered into the TSV
                    resume_where = "AFTER"
                # (else the last checked PNG either failed or didn't complete)
                # Don't check if the rest completed, just resume there and re-do it
            msg = f"You may want to resume {resume_where} the last URL: {last_url}"
            self.add(Log.ResumePoint, msg=msg, level=logging.CRITICAL)

    def halt(self):
        """
        Handle a shutdown before completion.
        """
        self.early_halt()
        self.suggest_resume()
        self.summarise()

    def successful_completion(self):
        """
        Give a reassuring congratulations in the event the program completes.
        """
        elapsed_t = self.time_since_init
        msg = f"Successful completion in {elapsed_t}."
        self.add(Log.HaltFinished, msg=msg, prefix="\n    ", level=logging.CRITICAL)
        msg = f"See {self.log_file} for full log."
        self.add(Log.LogNotify, msg=msg, level=logging.CRITICAL)

    def complete(self):
        """
        Handle a shutdown upon completion.
        """
        self.successful_completion()
        self.summarise()

    def summarise(self):
        """
        Log a summary upon finishing
        """
        prefix = "    "
        line = "-" * 58
        nice_line = f"{prefix}{line}\n"
        summary = f"{self.logs!r}"
        msg = f"Thank you for scraping with Wikitransp :^)-|-<\n"
        msg += nice_line
        max_k_len = max(len(k) for k in self.logs)
        log_summaries = {
            k.ljust(max_k_len): self.summarise_log_records(which_name=k)
            for k in self.logs
        }
        fmt_summaries = "\n".join([f"{k} : {v}" for k, v in log_summaries.items()])
        nice_logs = f"\n{prefix}".join(fmt_summaries.split("\n"))
        msg += prefix + nice_logs
        msg += "\n" + nice_line
        self.add(Log.BonVoyage, msg=msg, prefix="\n    ", level=logging.CRITICAL)

    def summarise_log_records(self, which_name: str) -> str:
        which = Log[which_name]  # enum from member name
        summary = {}
        max_count = max(len(self.logs[k]) for k in self.logs)
        max_count_chars = len(str(max_count))
        if self.has_event(which=which):
            entries = self.logs[which_name]
            n_records = len(entries)
            summary.update({"n": str(n_records).ljust(max_count_chars)})
            durations = [e.duration for e in entries if e.duration is not None]
            assert None not in durations  # give mypy a clue
            if durations:
                total_durations = sum(durations)
                assert total_durations is not None  # give mypy a clue
                mean_duration = total_durations / len(durations)
                summary.update({"μ": f"{mean_duration:.4f}"})
                summary.update({"min": f"{min(durations):.4f}"})
                summary.update({"max": f"{max(durations):.4f}"})
        else:
            n_records = 0
            summary.update({"records": str(n_records)})
        summary_str = ", ".join(f"{k}={v}" for k, v in summary.items())
        return summary_str

    def add(
        self,
        what: Log,
        msg: str = "",
        *,
        since: Log | None = None,
        prefix: str = "    ",
        suffix: str | None = None,
        level=None,
    ) -> None:
        """
        Add an event with a given type (``what``) along with the current time
        and any provided message (``msg``). Optionally, also give another event type
        to calculate the elapsed time since (``since``).

        Args:
          what            : The type of the event
          msg             : Any message passed with the event/constructed in the logger
          since           : (Optional) The type of event prior to this one, to calculate
                            relative time from (appending the difference to the ``msg``)
          prefix          : (Optional) Line prefix, to highlight a particular log record
          suffix          : (Optional) Line suffix, the line ending printed for the
                            record. If ``None`` (default), uses the Logger's default.
        """
        if level is None:
            level = self.log_level
        if self.is_in_filters(which=what):
            when = time.time()
            if since is None:
                prev_event = None
            else:
                # `since` is a `Log` enum whose integer value is less than the `what`
                # indicating a time to calculate relative to
                if since.value > what.value:
                    err_msg = f"Mis-specified timer: {since.value=} > {what.value=}"
                    self.error(msg=err_msg)
                    return  # Warn without raising, effectively
                prev_event = self.get_prior_event(which=since)
            event = Event(
                which=what, when=when, msg=msg, prev=prev_event, simple_repr=self.simple
            )
            empty_list: list[Event] = []
            self.logs.setdefault(what.name, empty_list)
            log_list = self.logs.get(what.name)
            assert isinstance(log_list, list)  # give mypy a clue
            log_list.append(event)
            if suffix is None:
                suffix = self.LINE_ENDING
            self.write_event(level=level, event=event, prefix=prefix, suffix=suffix)

    def has_event(self, which: Log) -> bool:
        """
        Whether the  :class:`~wikitransp.scraper.logger.Log` type ``which`` has been
        logged in the :attr:`~wikitransp.scraper.logger.Logger.logs` records yet
        (meaning it's safe to access it).

        Args:
          which : The Log enum record type (i.e. the type of the event).
        """
        return which.name in self.logs

    def get_prior_event(self, which: Log) -> Event:
        """
        Return the last logged :class:`~wikitransp.scraper.logger.Event` for the
        :class:`~wikitransp.scraper.logger.Log` type ``which``.

        Args:
          which : The Log enum record type (i.e. the type of the event).
        """
        log_list = self.get_logs(which=which)
        return log_list[-1]

    def get_duration_between_prior_events(
        self, which0: Log, which1: Log, internal: bool = False
    ) -> float | None:
        """
        Return the duration between the most recent events of type ``which0`` and
        ``which1`` (taking place in that order).

        May return ``None`` if the input are invalid and it's an internal log procedure
        (to avoid erroring it must return ``None``).

        Args:
          which0   : The first event type
          which1   : The second event type
          internal : Whether to log errors internally if (``True``) or raise them
        """
        t0 = self.get_prior_event(which=which0).when
        t1 = self.get_prior_event(which=which1).when
        which_vals = f"{which0=}: {t0=}, {which1=}: {t1=}"
        if any(t is None for t in (t0, t1)):
            err_msg = f"Did not get two durations to compare for {which_vals}"
            if internal:
                self.error(msg=err_msg)
                return None
            else:
                raise ValueError(err_msg)
        elif t0 > t1:
            # Rather than just switch them, error in case of a mistaken assumption
            err_msg = f"t0 did not take place before t1: {which_vals}"
            if internal:
                self.error(msg=err_msg)
                return None
            else:
                raise ValueError(err_msg)
        else:
            td = t1 - t0
            return td

    @overload
    def get_mean_duration(
        self,
        which: Log,
        extra: list[float] | None = None,
        internal: Literal[False] = False,
    ) -> float:
        ...

    @overload
    def get_mean_duration(
        self,
        which: Log,
        extra: list[float] | None,  # no default value as positional arg follows
        internal: Literal[True],
    ) -> float | None:
        ...

    def get_mean_duration(
        self,
        which: Log,
        extra: list[float] | None = None,
        internal: bool = False,
    ) -> float | None:
        """
        Get the mean duration for a particular log event type, extending the list
        before averaging if one is provided.

        Args:
          which : The Log enum record type (i.e. the type of the event).
          extra : List of durations to extend the list of durations by before averaging
        """
        if extra is None:
            extra = []
        if self.has_event(which=which):
            durations = self.get_durations(which=which)
        else:
            durations = []
        if extra:  # if non-empty list
            # Either an in/valid list
            if None in extra:  # invalid
                err_msg = "One or more of the extra durations to average were None"
                if internal:
                    self.error(msg=err_msg)
                    return None
                else:
                    raise ValueError(err_msg)
        # Valid extra values were passed in to use before averaging
        total_duration = sum(durations) + sum(extra)
        total_events = len(durations) + len(extra)
        assert total_duration is not None  # give mypy a clue
        mean_td = total_duration / total_events
        return mean_td

    def error(
        self,
        which: Log = Log.InternalLogException,
        msg: str = "",
        *,
        err: Exception | None = None,
    ) -> None:
        """
        Log an internal error message (without raising an error).

        Args:
          which : Type of :class:`~wikitransp.scraper.logger.Log` (default:
                  ``Log.InternalLogException``)
          msg   : Any message passed with the event (or constructed in the logger)
          err   : An error to be formatted onto the end of the message
        """
        if err is not None:
            msg += repr(err).replace("\n", " ")
        self.add(what=which, msg=msg, level=logging.ERROR)

    def fail(self, err: Exception):
        """
        Record the failure and increment the count of consecutive failures. When this
        count reaches :attr:`~wikitransp.logger.Logger.fail_limit`, a
        :class:`~wikitransp.logger.MaxLogFailureError` will be thrown.

        Args:
          err : The most recent error.
        """
        if self.consecutive_failures > 0:
            self.error(msg=f"{self.consecutive_failures=}")
        self.consecutive_failures += 1
        if self.consecutive_failures > self.fail_limit:
            self.summarise()
            exc = MaxLogFailureError(log=self)
            self.error(err=exc)
            raise exc from err

    def succeed(self):
        msg = f"Succeeded"
        if self.consecutive_failures > 0:
            msg += f" (resetting {self.consecutive_failures=} to 0)"
        self.add(Log.PngSuccess, msg=msg)
        self.consecutive_failures = 0

    def get_durations(self, which: Log) -> list[float]:
        """
        Return the :attr:`~wikitransp.scraper.logger.Event.duration` attributes
        stored for each of the logged events of
        :class:`~wikitransp.scraper.logger.Log` type ``which``. This means
        how long each of the logged steps took since the previous event they were
        timed against. May contain ``None`` if no duration was calculated,
        else will store a list of floats (the calculated duration in seconds).

        Args:
          which : The Log enum record type (i.e. the type of the event).
        """
        log_list = self.get_logs(which=which)
        return [e.duration for e in log_list if e.duration is not None]

    def get_last_duration(self, which: Log) -> float | None:
        """
        Return the :attr:`~wikitransp.scraper.logger.Event.duration` attribute
        stored for the most recent logged event of
        :class:`~wikitransp.scraper.logger.Log` type ``which``. This means how long the
        logged step took since the previous event it was timed against. May be ``None``
        if no duration was calculated, else will be a :class:`float` (the calculated
        duration in seconds).

        Args:
          which : The Log enum record type (i.e. the type of the event).
        """
        return self.get_prior_event(which=which).duration

    def get_logs(self, which: Log) -> list[Event]:
        """
        Return the :class:`~wikitransp.scraper.logger.Event` log entries for the
        :class:`~wikitransp.scraper.logger.Log` type ``which``.

        Args:
          which : The Log enum record type (i.e. the type of the event).
        """
        if not self.has_event(which=which):
            err_msg = f"Mis-specified timer: {which.name=} not in {[*self.logs]=}"
            self.error(msg=err_msg)
        log_list = self.logs.get(which.name)
        try:
            assert log_list is not None
        except:
            raise AssertionError(f"{which.name=} not in {log_list}")
        if len(log_list) == 0:
            err_msg = f"Mis-specified timer: {which.name=} not in {[*self.logs]=}"
            self.error(msg=err_msg)
        return log_list


class Event:
    """
    An event in the log
    """

    def __init__(
        self,
        which: Log,
        when: float,
        msg: str = "",
        prev: Event | None = None,
        simple_repr: bool = True,
    ):
        """
        Log an event of type ``which`` at time ``when`` with message ``msg``. Optionally
        also record the elapsed time since a previous event along with this event
        (usually indicating how long the logged event ``which`` took to carry out).

        Args:
          which : The type of the event
          when  : When the event was logged
          msg   : Any message passed with the event (or constructed in the logger)
          prev  : (Optionally) A previous event
        """
        self.type = which
        self.when = when
        self.msg = msg
        self.prev = prev
        self.simple = simple_repr
        self.duration = self.elapsed

    @property
    def elapsed(self) -> float | None:
        return None if self.prev is None else (self.when - self.prev.when)

    def __elapsed_repr__(self, unit: str = "s", show_since_which: bool = False) -> str:
        """
        Readable representation of the elapsed time since the previous event (if any).
        Currently prefer just the 'in 0.123s' rather than '0.123s since XyzEvent'
        """
        assert self.prev is not None  # Checked before calling, give mypy a clue
        if show_since_which:
            r = f"{self.elapsed:.4f}{unit} since {self.prev.type.name}"
        else:
            r = f"in {self.elapsed:.4f}{unit}"
        return r

    def __repr__(self):
        """
        Show the event message (if any) after its type and time.
        """
        msg = f" ⠶ {self.msg}" if self.msg else ""
        elapsed = ""
        if self.prev:
            show_which = not self.simple
            elapsed_repr = self.__elapsed_repr__(show_since_which=show_which)
            elapsed += f" {elapsed_repr}"
        return f"{self.type.name}{msg}{elapsed}"
