"""Fixed, lossless core-skill cards derived from the existing catalog.

Cards are presentation data, not another eligibility or scoring policy. A run
manager prepares its provider once; requests copy the selected family's cached
cards without serializing or interpreting the catalog again.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json


CORE_CARDS_VERSION = "catalog-core-cards.v1"


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@lru_cache(maxsize=128)
def _family_cards(version, catalog_sha256, family, catalog_json):
    """Compile once per revision, catalog content and selected family.

    Cached values remain private. Public callers always receive deep copies,
    including nested catalog fields that future revisions may introduce.
    """
    catalog = json.loads(catalog_json)
    cards = [{**skill, "module_id": module["module_id"]}
             for module in catalog["families"][family]["modules"]
             for skill in module["skills"]]
    return {
        "cards": cards,
        "sha256": _sha(_canonical({"version": version, "family": family,
                                  "core_skills": cards})),
    }


class CoreSkillCards:
    """An immutable-by-interface provider for one catalog snapshot.

    Rebuild the provider when the catalog changes. Compatibility checking uses
    normal dictionary equality, so per-request access does not repeat JSON
    serialization, hashing, or card construction. It also rejects accidental
    use of a provider after its caller mutates the catalog in place.
    """

    __slots__ = ("_catalog", "_catalog_sha256", "_families", "_version")

    def __init__(self, catalog, *, version=CORE_CARDS_VERSION):
        self._catalog = deepcopy(catalog)
        self._version = version
        catalog_json = _canonical(self._catalog)
        self._catalog_sha256 = _sha(catalog_json)
        self._families = {
            family: _family_cards(version, self._catalog_sha256, family, catalog_json)
            for family in self._catalog["families"]
        }

    @property
    def version(self):
        return self._version

    @property
    def catalog_sha256(self):
        return self._catalog_sha256

    def for_family(self, family, *, catalog=None):
        if catalog is not None and catalog != self._catalog:
            raise ValueError("Core skill cards do not match the current catalog; rebuild the provider")
        return deepcopy(self._families[family]["cards"])

    def signature(self, family=None):
        """Return cache/fingerprint metadata, never mutable cached cards."""
        result = {"version": self._version, "catalog_sha256": self._catalog_sha256}
        if family is None:
            result["family_sha256"] = {
                name: value["sha256"] for name, value in self._families.items()
            }
        else:
            result.update(family=family, cards_sha256=self._families[family]["sha256"])
        return result
