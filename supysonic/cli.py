# coding: utf-8
#
# This file is part of Supysonic.
# Supysonic is a Python implementation of the Subsonic server API.
#
# Copyright (C) 2013-2019 Alban 'spl0k' Féron
#
# Distributed under terms of the GNU AGPLv3 license.

import argparse
import cmd
import getpass
import pipes  # replace by shlex once Python 2.7 supprt is dropped
import shlex
import sys
import time

from pony.orm import db_session, select
from pony.orm import ObjectNotFound

from .config import IniConfig
from .daemon.client import DaemonClient
from .daemon.exceptions import DaemonUnavailableError
from .db import Folder, User, init_database, release_database
from .managers.folder import FolderManager
from .managers.user import UserManager
from .scanner import Scanner


class TimedProgressDisplay:
    def __init__(self, stdout, interval=5):
        self.__stdout = stdout
        self.__interval = interval
        self.__last_display = 0
        self.__last_len = 0

    def __call__(self, name, scanned):
        if time.time() - self.__last_display > self.__interval:
            progress = "Scanning '{0}': {1} files scanned".format(name, scanned)
            self.__stdout.write("\b" * self.__last_len)
            self.__stdout.write(progress)
            self.__stdout.flush()

            self.__last_len = len(progress)
            self.__last_display = time.time()


class CLIParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        raise RuntimeError(message)


class SupysonicCLI(cmd.Cmd):
    prompt = "supysonic> "

    def _make_do(self, command):
        def method(obj, line):
            try:
                args = getattr(obj, command + "_parser").parse_args(shlex.split(line))
            except RuntimeError as e:
                self.write_error_line(str(e))
                return

            if hasattr(obj.__class__, command + "_subparsers"):
                try:
                    func = getattr(obj, "{}_{}".format(command, args.action))
                except AttributeError:
                    return obj.default(line)
                return func(
                    **{key: vars(args)[key] for key in vars(args) if key != "action"}
                )
            else:
                try:
                    func = getattr(obj, command)
                except AttributeError:
                    return obj.default(line)
                return func(**vars(args))

        return method

    def __init__(self, config, stderr=None, *args, **kwargs):
        cmd.Cmd.__init__(self, *args, **kwargs)

        if stderr is not None:
            self.stderr = stderr
        else:
            self.stderr = sys.stderr

        self.__config = config
        self.__daemon = DaemonClient(config.DAEMON["socket"])

        # Generate do_* and help_* methods
        for parser_name in filter(
            lambda attr: attr.endswith("_parser") and "_" not in attr[:-7],
            dir(self.__class__),
        ):
            command = parser_name[:-7]

            if not hasattr(self.__class__, "do_" + command):
                setattr(self.__class__, "do_" + command, self._make_do(command))

            if hasattr(self.__class__, "do_" + command) and not hasattr(
                self.__class__, "help_" + command
            ):
                setattr(
                    self.__class__,
                    "help_" + command,
                    getattr(self.__class__, parser_name).print_help,
                )
            if hasattr(self.__class__, command + "_subparsers"):
                for action, subparser in getattr(
                    self.__class__, command + "_subparsers"
                ).choices.items():
                    setattr(
                        self, "help_{} {}".format(command, action), subparser.print_help
                    )

    def write_line(self, line=""):
        self.stdout.write(line + "\n")

    def write_error_line(self, line=""):
        self.stderr.write(line + "\n")

    def do_EOF(self, line):
        return True

    do_exit = do_EOF

    def default(self, line):
        self.write_line("Unknown command %s" % line.split()[0])
        self.do_help(None)

    def postloop(self):
        self.write_line()

    def completedefault(self, text, line, begidx, endidx):
        command = line.split()[0]
        parsers = getattr(self.__class__, command + "_subparsers", None)
        if not parsers:
            return []

        num_words = len(line[len(command) : begidx].split())
        if num_words == 0:
            return [a for a in parsers.choices if a.startswith(text)]
        return []

    folder_parser = CLIParser(prog="folder", add_help=False)
    folder_subparsers = folder_parser.add_subparsers(dest="action")
    folder_subparsers.add_parser("list", help="Lists folders", add_help=False)
    folder_add_parser = folder_subparsers.add_parser(
        "add", help="Adds a folder", add_help=False
    )
    folder_add_parser.add_argument("name", help="Name of the folder to add")
    folder_add_parser.add_argument(
        "path", help="Path to the directory pointed by the folder"
    )
    folder_del_parser = folder_subparsers.add_parser(
        "delete", help="Deletes a folder", add_help=False
    )
    folder_del_parser.add_argument("name", help="Name of the folder to delete")
    folder_scan_parser = folder_subparsers.add_parser(
        "scan", help="Run a scan on specified folders", add_help=False
    )
    folder_scan_parser.add_argument(
        "folders",
        metavar="folder",
        nargs="*",
        help="Folder(s) to be scanned. If ommitted, all folders are scanned",
    )
    folder_scan_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force scan of already know files even if they haven't changed",
    )
    folder_scan_target_group = folder_scan_parser.add_mutually_exclusive_group()
    folder_scan_target_group.add_argument(
        "--background",
        action="store_true",
        help="Scan the folder(s) in the background. Requires the daemon to be running.",
    )
    folder_scan_target_group.add_argument(
        "--foreground",
        action="store_true",
        help="Scan the folder(s) in the foreground, blocking the processus while the scan is running.",
    )

    @db_session
    def folder_list(self):
        self.write_line("Name\t\tPath\n----\t\t----")
        self.write_line(
            "\n".join(
                "{0: <16}{1}".format(f.name, f.path)
                for f in Folder.select(lambda f: f.root)
            )
        )

    @db_session
    def folder_add(self, name, path):
        try:
            FolderManager.add(name, path)
            self.write_line("Folder '{}' added".format(name))
        except ValueError as e:
            self.write_error_line(str(e))

    @db_session
    def folder_delete(self, name):
        try:
            FolderManager.delete_by_name(name)
            self.write_line("Deleted folder '{}'".format(name))
        except ObjectNotFound as e:
            self.write_error_line(str(e))

    def folder_scan(self, folders, force, background, foreground):
        auto = not background and not foreground
        if auto:
            try:
                self.__folder_scan_background(folders, force)
            except DaemonUnavailableError:
                self.write_error_line(
                    "Couldn't connect to the daemon, scanning in foreground"
                )
                self.__folder_scan_foreground(folders, force)
        elif background:
            try:
                self.__folder_scan_background(folders, force)
            except DaemonUnavailableError:
                self.write_error_line(
                    "Couldn't connect to the daemon, please use the '--foreground' option"
                )
        elif foreground:
            self.__folder_scan_foreground(folders, force)

    def __folder_scan_background(self, folders, force):
        self.__daemon.scan(folders, force)

    def __folder_scan_foreground(self, folders, force):
        try:
            progress = self.__daemon.get_scanning_progress()
            if progress is not None:
                self.write_error_line(
                    "The daemon is currently scanning, can't start a scan now"
                )
                return
        except DaemonUnavailableError:
            pass

        extensions = self.__config.BASE["scanner_extensions"]
        if extensions:
            extensions = extensions.split(" ")

        scanner = Scanner(
            force=force,
            extensions=extensions,
            follow_symlinks=self.__config.BASE["follow_symlinks"],
            progress=TimedProgressDisplay(self.stdout),
            on_folder_start=self.__unwatch_folder,
            on_folder_end=self.__watch_folder,
        )

        if folders:
            fstrs = folders
            with db_session:
                folders = select(f.name for f in Folder if f.root and f.name in fstrs)[
                    :
                ]
            notfound = set(fstrs) - set(folders)
            if notfound:
                self.write_line("No such folder(s): " + " ".join(notfound))
            for folder in folders:
                scanner.queue_folder(folder)
        else:
            with db_session:
                for folder in select(f.name for f in Folder if f.root):
                    scanner.queue_folder(folder)

        scanner.run()
        stats = scanner.stats()

        self.write_line("Scanning done")
        self.write_line(
            "Added: {0.artists} artists, {0.albums} albums, {0.tracks} tracks".format(
                stats.added
            )
        )
        self.write_line(
            "Deleted: {0.artists} artists, {0.albums} albums, {0.tracks} tracks".format(
                stats.deleted
            )
        )
        if stats.errors:
            self.write_line("Errors in:")
            for err in stats.errors:
                self.write_line("- " + err)

    def __unwatch_folder(self, folder):
        try:
            self.__daemon.remove_watched_folder(folder.path)
        except DaemonUnavailableError:
            pass

    def __watch_folder(self, folder):
        try:
            self.__daemon.add_watched_folder(folder.path)
        except DaemonUnavailableError:
            pass

    user_parser = CLIParser(prog="user", add_help=False)
    user_subparsers = user_parser.add_subparsers(dest="action")
    user_subparsers.add_parser("list", help="List users", add_help=False)
    user_add_parser = user_subparsers.add_parser(
        "add", help="Adds a user", add_help=False
    )
    user_add_parser.add_argument("name", help="Name/login of the user to add")
    user_add_parser.add_argument(
        "-a", "--admin", action="store_true", help="Give admin rights to the new user"
    )
    user_add_parser.add_argument(
        "-p", "--password", help="Specifies the user's password"
    )
    user_add_parser.add_argument(
        "-e", "--email", default="", help="Sets the user's email address"
    )
    user_del_parser = user_subparsers.add_parser(
        "delete", help="Deletes a user", add_help=False
    )
    user_del_parser.add_argument("name", help="Name/login of the user to delete")
    user_admin_parser = user_subparsers.add_parser(
        "setadmin", help="Enable/disable admin rights for a user", add_help=False
    )
    user_admin_parser.add_argument(
        "name", help="Name/login of the user to grant/revoke admin rights"
    )
    user_admin_parser.add_argument(
        "--off",
        action="store_true",
        help="Revoke admin rights if present, grant them otherwise",
    )
    user_pass_parser = user_subparsers.add_parser(
        "changepass", help="Changes a user's password", add_help=False
    )
    user_pass_parser.add_argument(
        "name", help="Name/login of the user to which change the password"
    )
    user_pass_parser.add_argument("password", nargs="?", help="New password")

    @db_session
    def user_list(self):
        self.write_line("Name\t\tAdmin\tEmail\n----\t\t-----\t-----")
        self.write_line(
            "\n".join(
                "{0: <16}{1}\t{2}".format(u.name, "*" if u.admin else "", u.mail)
                for u in User.select()
            )
        )

    def _ask_password(self):  # pragma: nocover
        password = getpass.getpass()
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise ValueError("Passwords don't match")
        return password

    @db_session
    def user_add(self, name, admin, password, email):
        try:
            if not password:
                password = self._ask_password()  # pragma: nocover
            UserManager.add(name, password, email, admin)
        except ValueError as e:
            self.write_error_line(str(e))

    @db_session
    def user_delete(self, name):
        try:
            UserManager.delete_by_name(name)
            self.write_line("Deleted user '{}'".format(name))
        except ObjectNotFound as e:
            self.write_error_line(str(e))

    @db_session
    def user_setadmin(self, name, off):
        user = User.get(name=name)
        if user is None:
            self.write_error_line("No such user")
        else:
            user.admin = not off
            self.write_line(
                "{0} '{1}' admin rights".format("Revoked" if off else "Granted", name)
            )

    @db_session
    def user_changepass(self, name, password):
        try:
            if not password:
                password = self._ask_password()  # pragma: nocover
            UserManager.change_password2(name, password)
            self.write_line("Successfully changed '{}' password".format(name))
        except ObjectNotFound as e:
            self.write_error_line(str(e))


def main():
    config = IniConfig.from_common_locations()
    init_database(config.BASE["database_uri"])

    cli = SupysonicCLI(config)
    if len(sys.argv) > 1:
        cli.onecmd(" ".join(pipes.quote(arg) for arg in sys.argv[1:]))
    else:
        cli.cmdloop()

    release_database()


if __name__ == "__main__":
    main()
