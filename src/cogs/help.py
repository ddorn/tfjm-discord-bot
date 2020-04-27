from discord.ext.commands import MinimalHelpCommand


# This is mostly a copy paste of MinimalHelpCommand
# With updated defaults and styles to match what I like
class TfjmHelpCommand(MinimalHelpCommand):
    def __init__(self, **options):
        options.setdefault("no_category", "Autres")
        super().__init__(**options)

    def get_opening_note(self):
        """Text at the beginning of the help command."""

        command_name = self.invoked_with
        return (
            "`{0}{1} [commande]` permet d'avoir plus d'info sur une commande.\n"
            "Vous pouvez aussi utiliser `{0}{1} [catégorie]` "
            "pour plus d'infos sur une catégorie.".format(
                self.clean_prefix, command_name
            )
        )

    def get_command_signature(self, command):
        return "`%s`" % super().get_command_signature(command)

    def add_bot_commands_formatting(self, commands, heading):
        """Adds the minified bot heading with commands to the output.

        The formatting should be added to the :attr:`paginator`.

        The default implementation is a bold underline heading followed
        by commands separated by an EN SPACE (U+2002) in the next line.

        Parameters
        -----------
        commands: Sequence[:class:`Command`]
            A list of commands that belong to the heading.
        heading: :class:`str`
            The heading to add to the line.
        """

        if commands:
            # U+2002 Middle Dot
            self.paginator.add_line("__**%s**__" % heading)
            for c in commands:
                self.add_subcommand_formatting(c)
            self.paginator.add_line()

    def add_subcommand_formatting(self, command):
        """Adds formatting information on a subcommand.

        The formatting should be added to the :attr:`paginator`.

        The default implementation is the prefix and the :attr:`Command.qualified_name`
        optionally followed by an En dash and the command's :attr:`Command.short_doc`.

        Parameters
        -----------
        command: :class:`Command`
            The command to show information of.
        """
        fmt = "`{0}{1}` \N{EN DASH} {2}" if command.short_doc else "`{0}{1}`"
        self.paginator.add_line(
            fmt.format(self.clean_prefix, command.qualified_name, command.short_doc)
        )

    def add_aliases_formatting(self, aliases):
        """Adds the formatting information on a command's aliases.

        The formatting should be added to the :attr:`paginator`.

        The default implementation is the :attr:`aliases_heading` bolded
        followed by a comma separated list of aliases.

        This is not called if there are no aliases to format.

        Parameters
        -----------
        aliases: Sequence[:class:`str`]
            A list of aliases to format.
        """

        aliases_str = ", ".join("`%s`" % a for a in aliases)
        self.paginator.add_line(
            "**%s** %s" % (self.aliases_heading, aliases_str), empty=True
        )
