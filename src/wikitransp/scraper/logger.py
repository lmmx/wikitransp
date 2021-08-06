from __future__ import annotations

import time
from enum import Enum
from sys import stderr, stdout
from typing import Literal, overload, Type
import logging
from logging.handlers import RotatingFileHandler

from ..logs import _dir_path as logs_dir

__all__ = ["Logger", "Log", "Event"]


class Log(Enum):
    """
    The different types of logged event, in order of execution (with any non-specific
    event types, which don't need to be ordered relative to the rest, afterwards).
    """

    Init = 0
    MatchResume = 1
    CheckPng = 2
    PrePngStream = 3
    PngStream = 4
    PopulateChunks = 5
    DirectAlpha = 6
    ConfAlpha = 7
    WriteRow = 8
    ConfAlphaNeg = 9
    DirectAlphaNeg = 10
    PngDone = 11
    RoutineException = 12
    BanURLException = 13
    GarbageCollect = 14
    AverageTime = 15
    BonVoyage = 16
    InternalLogException = 17  # Non-specific


class Logger:
    """
    A logger class for the scraping procedure (in :mod:`wikitransp.scraper.check_png`).
    Initially did not use the :mod:`logging` module so has both levels and verbosity
    controls (may adapt/remove at a later date).
    """
    ADD_SILENTLY: bool = False
    DEFAULT_FILE_NAME: str = "wikitransp.log"

    def __init__(
        self,
        name: str = "",
        log_level: int = logging.DEBUG,
        console_level: int = logging.INFO,
        out=stdout,
        err=stderr,
        verbose=True,
        error_verbose=True,
        simple: bool = True,
        which: list[Log] | None = None,
        internal: bool = False,
        add_silently: bool = ADD_SILENTLY,
        line_ending: str = "\n",
        path: Path | None = None,
        n_logs: int = 5,
        term_headers: bool = False,
    ):
        """
        Create a logger writing events to ``out`` (default: STDOUT) and errors to
        ``err`` (default: STDERR), either of which may be silenced by the ``verbose``
        and ``error_verbose`` flags.

        Args:
          name          : The name for the logger (recommended: pass ``__name__`` from
                          the calling module to show the path within your package).
                          Default: ``''`` (the empty string), giving the root logger.
          log_level     : Default log file level (default: :obj:`logging.DEBUG`)
          console_level : Default console log level (default: :obj:`logging.INFO`)
          sample        : Whether the run is for the sample
          out           : Where to print event messages (default: STDOUT)
          err           : Where to print error messages (default: STDERR)
          verbose       : Whether to print logged event messages
          error_verbose : Whether to print logged error messages
          simple        : Whether to print duration simply in logs or with the event
                          the duration is in comparison to
          which         : A list of :class:`~wikitransp.scraper.logger.Log` enums, or
                          ``None``, which is interpreted to mean all enums.
          add_silently  : Whether the `add` method is silent, overriding verbosity on
                          a per-`add` basis (default: False, so the `add` method is by
                          default not silent). Change this when you want to avoid seeing
                          so many logs, but don't want to filter them out (in which case
                          that they'd not be logged at all).
          line_ending   : The default line ending for logs (default: "\n"), overridable
                          per-entry using the `add` method's ``suffix`` argument.
          path          : The path to write the log to (rotated up to ``n_logs`` times).
          n_logs        : The maximum number of log backups to keep in rotation (total)
          term_headers  : Whether to show log headers in the console logs.
        """
        self.name = name
        self.log_level = log_level
        self.console_level = console_level
        self.logs: dict[str, list[Event]] = {}
        self.OUT = out # to be decommisioned
        self.ERR = err # to be decommisioned
        self.VERBOSE = verbose
        self.ERROR_VERBOSE = error_verbose
        self.ADD_SILENTLY = add_silently
        self.LINE_ENDING = line_ending
        self.simple = simple
        self.path = path
        self.n_logs = n_logs
        self.prepare_logging(console_headers=term_headers)
        self.filter = [] if which is None else which
        self.add(Log.Init)

    @property
    def log_file(self) -> Path:
        """
        Path to the log output file
        """
        return logs_dir / self.DEFAULT_FILE_NAME if self.path is None else self.path

    def prepare_logging(
        self, console_headers: bool = False,
        log_format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
        datefmt="%m-%d %H:%M",
    ):
        """
        Prepare the custom logger. Note: if :meth:`logging.basicConfig` has been called
        already, it'll override the call within this method.
        """
        # Set up logging to file
        logging.basicConfig(
            level=logging.DEBUG, # Lowest named level: log all levels to file
            format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
            datefmt="%m-%d %H:%M",
            filename=self.log_file,
            filemode="w",
        )
        # Set up rotating file handler instead of basicConfig (single overwritten file)
        #rot_handler = RotatingFileHandler(
        #    filename=self.log_file,
        #    maxBytes=0,
        #    backupCount=self.n_logs
        #)
        #rot_handler.setLevel(self.log_level)
        #log_formatter = logging.Formatter(fmt=log_format, datefmt=datefmt)
        ## tell the handler to use this format
        #rot_handler.setFormatter(log_formatter)
        ## Add the log message handler to the logger
        #logging.getLogger(self.name).addHandler(rot_handler)
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
        logging.getLogger(self.name).addHandler(console)

        # Now, we can log to the root logger, or any other logger. First the root...
        logging.info("Here's an info log")
        logging.debug("Here's area1 debug before info")
        logging.info("Here's area1 info after debug")
        logging.warning("Here's area 2 warning before error")
        logging.error("Here's area 2 error after warning")

    @property
    def filter(self) -> list[Log] | None:
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
        return (self.filter == [] or which in self.filter) and (
            isinstance(which, Log)  # Ensure it's in the Enum
        )

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
        if msg and (self.ERROR_VERBOSE if is_error else self.VERBOSE):
            log_msg = (msg + line_ending) # N.B. ``msg`` may be multiline
            # Slice off a single newline if present at the end, so as to preserve
            # non-EOL newlines when splitting multi-line strings (but logged separately)
            log_lines = log_msg[:(-1 if log_msg.endswith("\n") else None)].split("\n")
            for log_line in log_lines:
                logging.getLogger(self.name).log(level=level, msg=log_line)

    def write_event(
        self, level: int, event: Event, only_msg: bool = False, prefix="", suffix: str = "\n"
    ) -> None:
        """
        Write the event's message to the appropriate STDOUT/STDERR handle
        (detecting if it's an error from the substring 'Exception' in the
        :class:`~wikitransp.scraper.logger.Log` type's name).
        """
        msg = event.msg if only_msg else prefix + repr(event)
        level = logging.ERROR if "Exception" in event.type.name else level
        self.write_message(
            msg=msg,
            level=level,
            line_ending=suffix,
        )

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
        unsilence = self.ADD_SILENTLY  # toggle silencer if it's on, to unsilence
        self.add(Log.BonVoyage, msg=msg, prefix="\n    ", level=logging.INFO)

    def summarise_log_records(self, which_name: str) -> dict:
        which = Log[which_name]  # enum from member name
        summary = {}
        max_count_chars = len(str(max(len(self.logs.get(k)) for k in self.logs)))
        if self.has_event(which=which):
            entries = self.logs.get(which_name)
            n_records = len(entries)
            summary.update({"n": str(n_records).ljust(max_count_chars)})
            durations = [e.duration for e in entries]
            if None not in durations:
                mean_duration = sum(durations) / len(durations)
                summary.update({"μ": f"{mean_duration:.4f}"})
                summary.update({"min": f"{min(durations):.4f}"})
                summary.update({"max": f"{max(durations):.4f}"})
        else:
            n_records = 0
            summary.update({"records": n_records})
        summary_str = ""
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
        toggle_silencer=False,
        level = None,
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
          toggle_silencer : Whether to toggle the Logger's default silencing for newly
                            added events for this one (default: False).
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
            silent = self.ADD_SILENTLY ^ toggle_silencer
            if not silent:
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
        extra: list[float | None] | None = None,
        internal: Literal[False] = False,
    ) -> float:
        ...

    @overload
    def get_mean_duration(
        self,
        which: Log,
        extra: list[float | None] | None,  # no default value as positional arg follows
        internal: Literal[True],
    ) -> float | None:
        ...

    def get_mean_duration(
        self,
        which: Log,
        extra: list[float | None] | None = None,
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
            if None in durations:
                err_msg = "One or more of the durations to average were None"
                if internal:
                    self.error(msg=err_msg)
                    return None
                else:
                    raise ValueError(err_msg)
        else:
            durations = []
        assert None not in durations  # give mypy a clue
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

    def error(self, msg: str) -> None:
        """
        Log an internal error message (without raising an error).
        """
        self.add(Log.InternalLogException, msg=msg, level=logging.ERROR)

    def get_durations(self, which: Log) -> list[float | None]:
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
        return [e.duration for e in log_list]

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
