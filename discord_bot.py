import io, discord
from discord import app_commands, ui
from PIL import Image
from utils import load_toml_as_dict
from window_controller import WindowController

try:
    from early_access.early_access import register_early_access_commands
    early_access = True
except ImportError:
    early_access = False
    def register_early_access_commands(bot): pass

class BrawlPushModal(ui.Modal, title="Push Verification"):
    def __init__(self, bot_instance):
        super().__init__()
        self.bot = bot_instance

    brawler_name = ui.TextInput(
        label="Brawlers name?",
        placeholder="Epstein...",
        required=True,
        max_length=999999
    )
    
    push_to = ui.TextInput(
        label="Push to ?",
        placeholder="69000...",
        required=True,
        max_length=999999
    )
    
    cubes_now = ui.TextInput(
        label="Cubes rn ?",
        placeholder="67000...",
        required=True,
        max_length=999999
    )

class DiscordBot:
    def __init__(self, runtime_manager, data_service):
        self.runtime_manager = runtime_manager
        self.data_service = data_service
        self.window_controller: WindowController = None
        self.started = False
        
        self._cached_auth_user_id = None
        self._cached_guild_id = None
        self._load_cached_config()

        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)
        
        self.register_events()
        self.register_commands()
        register_early_access_commands(self)

    def _load_cached_config(self):
        config = load_toml_as_dict("cfg/webhook_config.toml", cache=True)
        self._cached_auth_user_id = self._extract_discord_id(config.get("discord_id", ""))
        self._cached_guild_id = self._extract_discord_id(config.get("discord_guild_id", ""))

    def set_window_controller(self, window_controller):
        self.window_controller = window_controller

    @staticmethod
    def _extract_discord_id(value):
        if not value:
            return None
        digits = "".join(ch for ch in str(value).strip() if ch.isdigit())
        return int(digits) if digits else None

    def get_authorized_user_id(self):
        if self._cached_auth_user_id is None:
            self._load_cached_config()
        return self._cached_auth_user_id

    def get_configured_guild_id(self):
        if self._cached_guild_id is None:
            self._load_cached_config()
        return self._cached_guild_id

    def get_configured_guild(self):
        guild_id = self.get_configured_guild_id()
        return discord.Object(id=guild_id) if guild_id else None

    async def require_authorized_user(self, interaction: discord.Interaction) -> bool:
        authorized_user_id = self.get_authorized_user_id()
        if authorized_user_id is None:
            await interaction.response.send_message(
                "❌ Discord remote control is disabled because `discord_id` is not configured.",
                ephemeral=True
            )
            return False

        if interaction.user.id != authorized_user_id:
            await interaction.response.send_message(
                "⚠️ You are not authorized to control this Pyla instance.",
                ephemeral=True
            )
            return False

        configured_guild_id = self.get_configured_guild_id()
        if configured_guild_id and interaction.guild_id and interaction.guild_id != configured_guild_id:
            await interaction.response.send_message(
                "❌ This Pyla instance is not configured for use on this Discord server.",
                ephemeral=True
            )
            return False

        return True

    async def sync_commands(self):
        guild = self.get_configured_guild()
        if guild:
            self.tree.copy_global_to(guild=guild)
            commands = await self.tree.sync(guild=guild)
            return len(commands), "guild"
        
        commands = await self.tree.sync()
        return len(commands), "global"

    def register_events(self):
        @self.client.event
        async def on_ready():
            print(f"[Discord] Bot {self.client.user.name} logged in successfully.")
            synced, scope = await self.sync_commands()
            print(f"[Discord] Synced {synced} commands ({scope}).")

    def register_commands(self):
        
        @self.tree.command(name="add_to_queue_modal", description="Open a modal form to add a brawler to the queue")
        async def add_to_queue_modal(interaction: discord.Interaction):
            if not await self.require_authorized_user(interaction):
                return
                
            status = self.runtime_manager.get_status()
            if status.get("is_running"):
                await interaction.response.send_message(
                    "❌ Cannot modify queue configuration while the bot execution thread is active.", 
                    ephemeral=True
                )
                return

            await interaction.response.send_modal(BrawlPushModal(self))

        @self.tree.command(name="screenshot", description="Get a screenshot of the current game window")
        async def screenshot(interaction: discord.Interaction):
            if not await self.require_authorized_user(interaction):
                return

            if not self.window_controller:
                await interaction.response.send_message("❌ Window controller not initialized. Is the bot core active?", ephemeral=True)
                return

            screenshot_frame = self.window_controller.screenshot()
            if screenshot_frame is None:
                await interaction.response.send_message("❌ Failed to grab screenshot. Stream might be closed.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            
            screenshot_buffer = io.BytesIO()
            Image.fromarray(screenshot_frame).save(screenshot_buffer, format="PNG", optimize=True)
            screenshot_buffer.seek(0)

            await interaction.followup.send(
                content="📸 **Current Game Window State:**",
                file=discord.File(screenshot_buffer, filename="screenshot.png")
            )

        @self.tree.command(name="stop", description="Makes the bot stop once it reaches the lobby")
        async def stop(interaction: discord.Interaction):
            if not await self.require_authorized_user(interaction):
                return

            status = self.runtime_manager.get_status()
            state = status.get("state", "idle")

            if state in ("idle", "error") or not status.get("is_running"):
                msg = f"❌ The bot is not currently running. State: `{state}`"
                if state == "error":
                    msg += f"\nLast Error: `{status.get('last_error')}`"
                await interaction.response.send_message(msg, ephemeral=True)
                return

            if state in ("stopping", "pausing"):
                await interaction.response.send_message(f"⏳ Bot is already in `{state}` transition. Please hold.", ephemeral=True)
                return

            res = self.runtime_manager.stop()
            prefix = "✅ Success" if res.get("ok") else "❌ Failed"
            await interaction.response.send_message(f"{prefix}! {res.get('message', '')}", ephemeral=True)

        @self.tree.command(name="pause", description="Makes the bot pause once it reaches the lobby")
        async def pause(interaction: discord.Interaction):
            if not await self.require_authorized_user(interaction):
                return

            status = self.runtime_manager.get_status()
            state = status.get("state", "idle")

            if state in ("idle", "error") or not status.get("is_running"):
                msg = f"❌ The bot is not running. State: `{state}`"
                if state == "error":
                    msg += f"\nLast Error: `{status.get('last_error')}`"
                await interaction.response.send_message(msg, ephemeral=True)
                return

            if state in ("pausing", "paused", "stopping"):
                await interaction.response.send_message(f"⏸️ Bot state is already `{state}`.", ephemeral=True)
                return

            res = self.runtime_manager.pause()
            prefix = "✅ Success" if res.get("ok") else "❌ Failed"
            await interaction.response.send_message(f"{prefix}! {res.get('message', '')}", ephemeral=True)

        @self.tree.command(name="start", description="Starts the bot if it's not already running")
        async def start(interaction: discord.Interaction):
            if not await self.require_authorized_user(interaction):
                return

            start_result = self.runtime_manager.start_current_queue(self)
            prefix = "✅ Success" if start_result.get("ok") else "❌ Failed"
            await interaction.response.send_message(f"{prefix}! {start_result.get('message', '')}", ephemeral=True)

        @self.tree.command(name="status", description="Returns the current status of the bot")
        async def status(interaction: discord.Interaction):
            if not await self.require_authorized_user(interaction):
                return

            status_data = self.runtime_manager.get_status()
            if not status_data.get("is_running"):
                await interaction.response.send_message("💤 The bot is currently **not running** (Idle).", ephemeral=True)
                return

            state = status_data.get("state", "unknown").upper()
            embed = discord.Embed(title="🤖 Pyla Instance Status", color=discord.Color.blue())
            embed.add_field(name="Core State", value=f"`{state}`", inline=True)

            active_playstyle = self.data_service.get_playstyles_payload().get("current")
            playstyle_name = active_playstyle.get("name") if active_playstyle else "None"
            embed.add_field(name="Playstyle", value=f"`{playstyle_name}`", inline=True)

            last_error = status_data.get("last_error")
            if last_error:
                embed.add_field(name="⚠️ Last Registered Error", value=f"```{last_error}```", inline=False)

            embed.set_footer(text="Use /view_queue to inspect the active brawler queue.")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @self.tree.command(name="restart_brawl_stars", description="Restarts Brawl Stars if the bot is running")
        async def restart_brawl_stars(interaction: discord.Interaction):
            if not await self.require_authorized_user(interaction):
                return

            status = self.runtime_manager.get_status()
            if not status.get("is_running"):
                await interaction.response.send_message("❌ Cannot restart game process while bot core is offline.", ephemeral=True)
                return

            await interaction.response.send_message("🔄 **Force-restarting Brawl Stars activity inside the sandbox...**", ephemeral=True)
            self.window_controller.restart_brawl_stars()

        @self.tree.command(name="view_queue", description="View the current queue of the bot")
        async def view_queue(interaction: discord.Interaction):
            if not await self.require_authorized_user(interaction):
                return

            queue = self.data_service.get_queue_data()
            if not queue:
                await interaction.response.send_message("📭 The target queue is currently empty.", ephemeral=True)
                return

            embed = discord.Embed(title="📋 Core Execution Queue", color=discord.Color.green())
            chunk_text = ""
            responded = False

            for item in queue:
                brawler = item.get("brawler", "Unknown").capitalize()
                p_type = item.get("type", "Unknown")
                target = item.get("push_until", "0")
                current = item.get("trophies") if p_type == "trophies" else item.get("wins")
                auto = " 🤖 *(Auto-picked)*" if item.get("automatically_pick") else ""
                
                line = f"• **{brawler}**: `{current}/{target}` {p_type}{auto}\n"
                
                if len(chunk_text) + len(line) > 1024:
                    embed.description = chunk_text
                    if not responded:
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        responded = True
                    else:
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    embed = discord.Embed(title="📋 Core Execution Queue (Continued)", color=discord.Color.green())
                    chunk_text = ""
                
                chunk_text += line

            if chunk_text:
                embed.description = chunk_text
                if not responded:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(embed=embed, ephemeral=True)

        @self.tree.command(name="help", description="Show the list of available commands")
        async def help_command(interaction: discord.Interaction):
            if not await self.require_authorized_user(interaction):
                return

            embed = discord.Embed(
                title="📖 Pyla Remote Control Manual", 
                description="List of available slash operations to manage the Termux core runtime.",
                color=discord.Color.gold()
            )
            
            core_cmds = (
                ("`/start`", "Starts processing the current queue configuration."),
                ("`/stop`", "Safely terminates loop activities upon entering lobby context."),
                ("`/pause`", "Suspends action loops at next available safe state."),
                ("`/status`", "Inspect current state, loaded profiles, and operational issues."),
                ("`/screenshot`", "Capture current display frame parameters asynchronously."),
                ("`/view_queue`", "Get an inspection layout of the runtime queue targets."),
                ("`/add_to_queue_modal`", "Open a visual window to configure a push profile."),
                ("`/restart_brawl_stars`", "Force-kill and cycle the application instance via ADB interface.")
            )
            
            ea_cmds = (
                ("`/add_to_queue`", "Appends targeted parameters to current active queue."),
                ("`/remove_from_queue`", "Removes active structural node entries."),
                ("`/clear_queue`", "Wipes memory array allocations of tracking records."),
                ("`/activate_playstyle`", "Overwrites the current tactical action rule profile matrix.")
            )

            for cmd, desc in core_cmds:
                embed.add_field(name=cmd, value=desc, inline=False)
                
            ea_prefix = "⭐ Early Access Operations" if early_access else "🔒 Early Access Operations (Locked)"
            ea_content = ""
            for cmd, desc in ea_cmds:
                ea_content += f"**{cmd}**: {desc}\n"
            
            embed.add_field(name=ea_prefix, value=ea_content, inline=False)

            if not early_access:
                embed.add_field(
                    name="🔓 Unlock Features", 
                    value="Obtain early-access runtime binaries from the premium community dashboard:\n<https://discord.com/channels/1205263029269438574/1233146889843769417>",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

    def run_bot(self):
        config = load_toml_as_dict("cfg/webhook_config.toml", cache=True)
        discord_bot_token = str(config.get("discord_bot_token", "")).strip()
        
        if not discord_bot_token:
            print("[Discord] Token not specified inside configs. Operational module skipping execution.")
            return
        if self.started:
            return

        self.started = True
        try:
            self.client.run(discord_bot_token)
        finally:
            self.started = False
