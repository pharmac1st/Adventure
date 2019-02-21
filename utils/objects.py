# -> Builtin modules
import asyncio
import enum
import logging
import operator
from datetime import datetime, timedelta

# -> Pip packages
import humanize

# -> Local files
import utils

maplog = logging.getLogger("Adventure.MapManager")
plylog = logging.getLogger("Adventure.PlayerManager")


class Status(enum.Enum):
    idle = 0
    travelling = 1
    exploring = 2


class Map:
    __slots__ = ("id", "name", "nearby", "_nearby", "density", "_raw", "description")

    def __init__(self, **kwg):
        self._raw = kwg.copy()
        self.id = kwg.get("id")
        self.name = kwg.get("name")
        self.nearby = list()
        self.density = kwg.get("density")
        self.description = kwg.get("description")
        self._nearby = []

    def _mini_repr(self):
        return f"<Map id={self.id} name={self.name}>"

    def __repr__(self):
        return f"<Map id={self.id} name='{self.name}' nearby={set(map(self.__class__._mini_repr, self.nearby))}>"

    def __eq__(self, other):
        return isinstance(other, type(self)) and other.id == self.id

    def __str__(self):
        return self.name

    def __int__(self):
        return self.id

    def calculate_travel_to(self, other) -> float:
        if not isinstance(other, Map):
            raise ValueError("Must be a Map object.")
        return (self.density + other.density) / 1234

    def calculate_explore(self) -> float:
        return (self.density * 1234) / (1000 ** 2)


class Player:
    __slots__ = ("owner", "name", "_map", "_bot", "_next_map", "created_at", "_explored_maps", "status")

    def __init__(self, **kwg):
        self._bot = kwg.get("bot")
        self.owner = kwg.get("owner")
        self.name = kwg.get("name")
        self._map = self._bot.map_manager.get_map(0)
        self._next_map: Map = None
        self.created_at = kwg.get("created_at")
        self._explored_maps = kwg.get("explored", [self._bot.map_manager.get_map(0)])
        self.status = kwg.get("status", Status.idle)

    def __repr__(self):
        return "<Player name='{0.name}' owner={0.owner!r} map={0.map!r}>".format(self)

    def __str__(self):
        return self.name

    @property
    def explored_maps(self):
        return self._explored_maps

    @explored_maps.setter
    def explored_maps(self, value):
        self._explored_maps = list(map(self._bot.map_manager.get_map, value))

    @property
    def is_admin(self):
        return self.owner.id in self._bot.config.OWNERS

    @property
    def map(self):
        return self._map

    @map.setter
    def map(self, value):
        self._map = self._bot.map_manager.resolve_map(value)

    # -- Checks -- #

    async def is_travelling(self) -> bool:
        return await self.travel_time() > 0

    async def is_exploring(self) -> bool:
        return await self.explore_time() > 0

    # -- Updaters -- #

    async def update_travelling(self):
        await asyncio.sleep(1)
        if await self.is_travelling():
            if self._next_map is None:
                dest = await self._bot.redis.execute("GET", f"next_map_{self.owner.id}")
                self._next_map = self._bot.map_manager.get_map(dest)
            return  # the TTL hasnt expired
        if self._next_map is None:
            dest = await self._bot.redis.execute("GET", f"next_map_{self.owner.id}")
        else:
            dest = self._next_map.id
        if dest is None:
            return  # the player isnt travelling at all
        self._next_map = None
        plylog.info("%s has arrived at their location.", self.name)
        self.map = dest
        await self._bot.redis.execute("DEL", f"next_map_{self.owner.id}")
        await self._bot.redis.execute("SET", f"status_{self.owner.id}", "0")
        self.status = Status.idle
        return True

    async def update_exploring(self):
        await asyncio.sleep(1)
        if await self.is_exploring():
            return
        if self.status == Status.exploring or await self._bot.redis.execute("GET", f"status_{self.owner.id}") == 2:
            plylog.info("%s has finished exploring %s.", self.name, self.map)
            await self._bot.redis.execute("SET", f"status_{self.owner.id}", "0")
            self.status = Status.idle
            return True

    async def travel_time(self):
        if not self.map:
            self.map = await self._bot.redis.execute("GET", f"next_map_{self.owner.id}")
        return await self._bot.redis.execute("TTL", f"travelling_{self.owner.id}")

    async def explore_time(self):
        return await self._bot.redis.execute("TTL", f"exploring_{self.owner.id}")

    # -- Real functions -- #

    async def travel_to(self, destination: Map):
        if await self.is_travelling():
            raise utils.AlreadyTravelling(self.name,
                                          humanize.naturaltime((datetime.now() + timedelta(
                                                          seconds=await self.travel_time()))))
        elif await self.is_exploring():
            raise utils.AlreadyTravelling(self.name,
                                          humanize.naturaltime((datetime.now() + timedelta(
                                                          seconds=await self.explore_time()))))
        time = int(((datetime.now() + timedelta(hours=self.map.calculate_travel_to(destination))) - datetime.now()
                    ).total_seconds())
        self._next_map = destination
        plylog.info("%s is adventuring to %s and will finish in %.2f hours.",
                    self.name, destination, self.map.calculate_travel_to(destination))
        await self._bot.redis.execute("SET", f"travelling_{self.owner.id}", str(time), "EX", str(time))
        await self._bot.redis.execute("SET", f"next_map_{self.owner.id}", str(destination.id))
        await self._bot.redis.execute("SET", f"status_{self.owner.id}", "1")
        self.status = Status.travelling

    async def explore(self):
        if await self.is_travelling():
            raise utils.AlreadyTravelling(self.name,
                                          humanize.naturaltime((datetime.now() + timedelta(
                                              seconds=await self.travel_time()))))
        elif await self.is_exploring():
            raise utils.AlreadyTravelling(self.name,
                                          humanize.naturaltime((datetime.now() + timedelta(
                                              seconds=await self.explore_time()))))
        if self.map in self._explored_maps:
            raise utils.AlreadyExplored(self.map)
        time = int(((datetime.now() + timedelta(hours=self.map.calculate_explore())) - datetime.now()).total_seconds())
        plylog.info("%s is exploring %s and will finish in %.2f hours.",
                    self.name, self.map, self.map.calculate_explore())
        await self._bot.redis.execute("SET", f"exploring_{self.owner.id}", str(time), "EX", str(time))
        await self._bot.redis.execute("SET", f"status_{self.owner.id}", "2")
        self.status = Status.exploring
        self._explored_maps.append(self.map)

    async def save(self, *, cursor=None):
        q = """
INSERT INTO players
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (owner_id)
DO UPDATE
SET name = $2, map_id = $3, explored = $5
WHERE players.owner_id = $1;
        """
        if not cursor:
            await self._bot.db.execute(q, self.owner.id, self.name, self._map.id, self.created_at,
                                       list(map(operator.attrgetter("id"), self.explored_maps)))
        else:
            await cursor.execute(q, self.owner.id, self.name, self._map.id, self.created_at,
                                 list(map(operator.attrgetter("id"), self.explored_maps)))

    async def delete(self, *, cursor=None):
        if not cursor:
            await self._bot.db.execute("DELETE FROM players WHERE owner_id=$1;", self.owner.id)
        else:
            await cursor.execute("DELETE FROM players WHERE owner_id=$1;", self.owner.id)
        await self._bot.redis.execute("DEL", f"travelling_{self.owner.id}")
        await self._bot.redis.execute("DEL", f"next_map_{self.owner.id}")
        await self._bot.redis.execute("DEL", f"exploring_{self.owner.id}")
        await self._bot.redis.execute("DEL", f"status_{self.owner.id}")
        self._bot.player_manager.players.remove(self)
        plylog.info("Player \"%s\" was deleted. (%s [%s])", self.name, self.owner, self.owner.id)
        del self


class Item:
    __slots__ = ("id", "name", "cost")

    def __init__(self, *, id: int, name: str, cost: float, **kwargs):
        self.id = id
        self.name = name
        self.cost = cost

    def __str__(self):
        return self.name

    def __repr__(self):
        return "<Item name=\"{0.name}\" id={0.id} cost={0.cost:.2f}>".format(self)

    @classmethod
    async def without_id(cls, db, *, name: str, cost: float):
        _id = await db.fetchval("INSERT INTO shop VALUES ($1, $2) RETURNING item_id;", name, cost)
        return cls(id=_id, name=name, cost=cost)

    def price(self) -> float:
        """
        The sell price of the item.
        """

    async def save(self, db):
        await db.execute("UPDATE shop SET name=$1, cost=$2 WHERE item_id=$3;", self.name, self.cost, self.id)
