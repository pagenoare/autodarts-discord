import json
from keycloak import KeycloakOpenID
import requests
import rich
import discord
import websockets
import rich_click as click

AUTODART_AUTH_URL = "https://login.autodarts.io/"
AUTODART_AUTH_TICKET_URL = "https://api.autodarts.io/ms/v0/ticket"
AUTODART_CLIENT_ID = "autodarts-app"
AUTODART_REALM_NAME = "autodarts"
AUTODART_WEBSOCKET_URL = "wss://api.autodarts.io/ms/v0/subscribe?ticket="


class AutodartsBot(discord.Client):
    def __init__(self, user_email, user_password, discord_channel_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        access_token = self._receive_token_autodarts(user_email, user_password)

        ticket = requests.post(
            AUTODART_AUTH_TICKET_URL,
            headers={"Authorization": "Bearer " + access_token},
        )
        self.ws_uri = AUTODART_WEBSOCKET_URL + ticket.text
        self.seen_events = []
        self.channel_id = discord_channel_id

    def _receive_token_autodarts(self, user_email, user_password):
        try:
            # Configure client
            keycloak_openid = KeycloakOpenID(
                server_url=AUTODART_AUTH_URL,
                client_id=AUTODART_CLIENT_ID,
                realm_name=AUTODART_REALM_NAME,
                verify=True,
            )
            token = keycloak_openid.token(user_email, user_password)
            accessToken = token["access_token"]
            return accessToken
        except Exception as e:
            rich.print("Receive token failed", e)

    async def setup_hook(self) -> None:
        self.bg_task = self.loop.create_task(self.listen_lobbies())

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

    async def _handle_msg(self, channel, msg):
        rich.print(msg)
        if msg["data"]["isPrivate"]:
            return

        data = msg["data"]
        lobby_id = data["id"]
        url = f"https://autodarts.io/lobbies/{lobby_id}"
        embed = discord.Embed(title="New public lobby has been opened", url=url)
        embed.set_author(name=data["host"]["name"], icon_url=data["host"]["avatarUrl"])
        embed.add_field(name="Game Mode", value=data["variant"])
        embed.add_field(name="Bull-off", value=data["bullOffMode"])
        if data["settings"]:
            for name, value in data["settings"].items():
                embed.add_field(name=name, value=value)

        if msg["topic"] not in self.seen_events:
            await channel.send(embed=embed)

        self.seen_events.append(msg["topic"])

    async def listen_lobbies(self):
        await self.wait_until_ready()
        channel = self.get_channel(self.channel_id)

        async with websockets.connect(self.ws_uri) as websocket:
            paramsSubscribeLobbiesEvents = {
                "channel": "autodarts.lobbies",
                "type": "subscribe",
                "topic": "*.state",
            }
            await websocket.send(json.dumps(paramsSubscribeLobbiesEvents))
            while not self.is_closed():
                msg = await websocket.recv()
                msg = json.loads(msg)
                await self._handle_msg(channel, msg)


@click.command()
@click.option("--autodarts-email", type=str, required=True)
@click.option("--autodarts-password", type=str, required=True)
@click.option("--discord-token", type=str, required=True)
@click.option("--discord-channel-id", type=int, required=True)
def main(autodarts_email, autodarts_password, discord_token, discord_channel_id):
    client = AutodartsBot(
        autodarts_email,
        autodarts_password,
        discord_channel_id,
        intents=discord.Intents.default(),
    )
    client.run(discord_token)


if __name__ == "__main__":
    main()
