"""Content for the demo: places, their photo catalogue, storytellers and seven stories.

The Arabic lines are placeholders written for the demo. A native speaker should review the
Jordanian dialect and MSA before the judging (see docs/DECISIONS.md).

Each story line gives the same sentence in every language it needs: the original language
(`verbatim`), and the translations. MSA stories have no Jordanian line; English stories
have neither Arabic original.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlaceSeed:
    slug: str
    name: str
    latitude: float
    longitude: float
    cover: str
    # (photo slug = source file stem, caption)
    photos: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class StorytellerSeed:
    key: str
    display_name: str


@dataclass(frozen=True)
class StorySeed:
    key: str
    title: str
    category: str
    place: str  # place slug
    latitude: float
    longitude: float
    storyteller: str
    language: str  # jordanian | msa | english
    duration_ms: int
    published_days_ago: int
    curated: bool
    cover: str
    lines: tuple[dict[str, str], ...] = field(default_factory=tuple)


PLACES: tuple[PlaceSeed, ...] = (
    PlaceSeed(
        "petra", "Petra", 30.3285, 35.4444, "petra-treasury",
        (
            ("petra-treasury-hero", "The Treasury at Petra"),
            ("petra-treasury", "Al-Khazneh, the Treasury"),
            ("petra-monastery", "Ad Deir, the Monastery"),
            ("petra-theater", "The Petra theatre"),
            ("nabataean-water-channels", "Nabataean water channels"),
            ("petra-siq", "The Siq"),
        ),
    ),
    PlaceSeed(
        "amman", "Amman", 31.9539, 35.9106, "amman-citadel",
        (
            ("amman-citadel", "Amman Citadel"),
            ("amman-citadel-day", "The Temple of Hercules"),
            ("amman-roman-theater", "The Roman Theatre"),
            ("balad-market", "Al-Balad market"),
            ("balad-market-2", "A street in Al-Balad"),
            ("spice-market", "The spice market"),
            ("amman-rainbow", "Rainbow Street"),
            ("amman-skyline", "The Amman skyline"),
            ("amman-boulevard", "Abdali Boulevard"),
        ),
    ),
    PlaceSeed(
        "madaba", "Madaba", 31.7167, 35.7939, "mosaic-workshop",
        (
            ("madaba-loom", "A loom in Madaba"),
            ("weaving-loom-2", "Weaving on the loom"),
            ("mosaic-workshop", "A mosaic workshop"),
            ("madaba-nebo", "Mount Nebo"),
            ("madaba-church", "St George's Church"),
            ("madaba-church-facade", "The facade of St George's"),
            ("madaba-market", "Madaba craft street"),
        ),
    ),
    PlaceSeed(
        "jerash", "Jerash", 32.2722, 35.8911, "jerash-columns-dusk",
        (
            ("jerash-columns-dusk", "Columns at dusk"),
            ("jerash-oval-plaza", "The Oval Plaza"),
            ("ceramic-workshop", "A ceramic workshop"),
            ("jerash-sand-art", "Sand art"),
        ),
    ),
    PlaceSeed(
        "wadi-rum", "Wadi Rum", 29.5759, 35.4204, "wadi-rum-sunset",
        (
            ("wadi-rum-sunset", "Sunset over Wadi Rum"),
            ("wadi-rum-camp", "A Bedouin camp"),
            ("wadi-rum-valley", "The desert valley"),
        ),
    ),
    PlaceSeed(
        "aqaba", "Aqaba", 29.532, 35.0063, "aqaba",
        (
            ("aqaba", "The Aqaba waterfront"),
            ("aqaba-beach", "Beach and marina"),
            ("aqaba-lagoon", "Lagoon and palms"),
            ("aqaba-lionfish", "A lionfish"),
            ("aqaba-tank-wreck", "Underwater museum: a tank"),
            ("aqaba-armored-car", "Underwater museum: an armoured car"),
            ("aqaba-c130", "Underwater museum: a C-130"),
        ),
    ),
)  # fmt: skip

STORYTELLERS: tuple[StorytellerSeed, ...] = (
    StorytellerSeed("um-ahmad", "Um Ahmad"),
    StorytellerSeed("zaid-j", "Zaid J."),
    StorytellerSeed("faisal-b", "Faisal B."),
    StorytellerSeed("abu-omar", "Abu Omar Al-Jerashi"),
    StorytellerSeed("abu-mahmoud", "Abu Mahmoud"),
    StorytellerSeed("sitti-fatima", "Sitti Fatima"),
    StorytellerSeed("sayegh", "The Sayegh Family"),
)


def _min(minutes: int, seconds: int = 0) -> int:
    return (minutes * 60 + seconds) * 1000


STORIES: tuple[StorySeed, ...] = (
    StorySeed(
        key="loom-of-ancestors",
        title="The Loom of Ancestors",
        category="crafts",
        place="madaba",
        latitude=31.716,
        longitude=35.7939,
        storyteller="um-ahmad",
        language="jordanian",
        duration_ms=_min(12),
        published_days_ago=20,
        curated=False,
        cover="weaving-loom-2",
        lines=(
            {
                "jordanian": "ستي علمتني النول وأنا عمري عشر سنين",
                "msa": "علّمتني جدتي النسج على النول عندما كنت في العاشرة من عمري",
                "english": "My grandmother taught me the loom when I was ten years old",
            },
            {
                "jordanian": "كانت تقول كل خيط إله حكاية وكل لون إله معنى",
                "msa": "كانت تقول إن لكل خيط حكاية ولكل لون معنى",
                "english": "She used to say every thread has a story and every colour a meaning",
            },
            {
                "jordanian": "الأحمر للفرح، والأسود للصبر، والأخضر للأرض",
                "msa": "الأحمر للفرح، والأسود للصبر، والأخضر للأرض",
                "english": "Red is for joy, black for patience, and green for the land",
            },
            {
                "jordanian": "هلأ أنا بعلّم بنات الحارة نفس النقشات",
                "msa": "والآن أعلّم فتيات الحي النقوش نفسها",
                "english": "Now I teach the girls of the neighbourhood the very same patterns",
            },
            {
                "jordanian": "عشان النقشة ما تموت معنا",
                "msa": "حتى لا يموت النقش معنا",
                "english": "So that the pattern does not die with us",
            },
        ),
    ),
    StorySeed(
        key="morning-steam",
        title="Morning Steam in Old Al-Balad",
        category="daily_life",
        place="amman",
        latitude=31.9497,
        longitude=35.9328,
        storyteller="zaid-j",
        language="jordanian",
        duration_ms=_min(8),
        published_days_ago=5,
        curated=False,
        cover="balad-market",
        lines=(
            {
                "jordanian": "بفتح الكشك قبل ما تطلع الشمس",
                "msa": "أفتح الكشك قبل أن تشرق الشمس",
                "english": "I open the kiosk before the sun comes up",
            },
            {
                "jordanian": "أول زبون دايماً سواق التكسي، بيشرب شاي بالميرمية",
                "msa": "أول زبون دائماً سائق سيارة الأجرة، يشرب الشاي بالمريمية",
                "english": "The first customer is always a taxi driver, drinking tea with sage",
            },
            {
                "jordanian": "أبوي وقف بنفس المحل أربعين سنة",
                "msa": "وقف أبي في المكان نفسه أربعين عاماً",
                "english": "My father stood in this same spot for forty years",
            },
            {
                "jordanian": "البلد تغيرت كثير، بس ريحة الشاي ما تغيرت",
                "msa": "تغيّرت البلد كثيراً، لكن رائحة الشاي لم تتغير",
                "english": "Downtown has changed a lot, but the smell of the tea has not",
            },
        ),
    ),
    StorySeed(
        key="echoes-red-desert",
        title="Echoes of the Red Desert",
        category="folklore",
        place="wadi-rum",
        latitude=29.5766,
        longitude=35.419,
        storyteller="faisal-b",
        language="jordanian",
        duration_ms=_min(15),
        published_days_ago=60,
        curated=True,
        cover="wadi-rum-sunset",
        lines=(
            {
                "jordanian": "بالليل بالبر، سيدي كان يعدّ النجوم بأساميها",
                "msa": "في الليل في الصحراء، كان جدي يعدّ النجوم بأسمائها",
                "english": "At night in the desert, my grandfather counted the stars by name",
            },
            {
                "jordanian": "كان يقول هاي النجمة بتدل على البير",
                "msa": "كان يقول إن هذه النجمة تدل على البئر",
                "english": "He would say that this star points the way to the well",
            },
            {
                "jordanian": "والقافلة اللي بتضيع، النجوم بترجعها",
                "msa": "والقافلة التي تضل طريقها تعيدها النجوم",
                "english": "And a caravan that loses its way is brought home by the stars",
            },
            {
                "jordanian": "إحنا ما كان عنا خرايط، كان عنا السما",
                "msa": "لم تكن لدينا خرائط، كانت لدينا السماء",
                "english": "We had no maps; we had the sky",
            },
            {
                "jordanian": "وهاي الأسامي أقدم من كل الخرايط",
                "msa": "وهذه الأسماء أقدم من كل الخرائط",
                "english": "And these names are older than any map",
            },
        ),
    ),
    StorySeed(
        key="echoes-of-jerash",
        title="The Echoes of Jerash",
        category="history",
        place="jerash",
        latitude=32.2808,
        longitude=35.8993,
        storyteller="abu-omar",
        language="jordanian",
        duration_ms=_min(18, 42),
        published_days_ago=30,
        curated=True,
        cover="jerash-columns-dusk",
        lines=(
            {
                "jordanian": "أهلا فيكم بجرش، مدينة الألف عمود",
                "msa": "أهلاً بكم في جرش، مدينة الألف عمود",
                "english": "Welcome to Jerash, the city of a thousand columns",
            },
            {
                "jordanian": "سيدي كان يقول كل حجر هون إله ذاكرة",
                "msa": "كان جدي يقول إن لكل حجر هنا ذاكرة",
                "english": "My grandfather used to say every stone here has a memory",
            },
            {
                "jordanian": "وإحنا صغار كنا نلعب بالساحة البيضاوية قبل الظهر",
                "msa": "عندما كنا صغاراً كنا نلعب في الساحة البيضاوية قبل الظهر",
                "english": "As children we played in the Oval Plaza before noon",
            },
            {
                "jordanian": "وظل الأعمدة كان يمتد مثل أصابع كبيرة على الحجر",
                "msa": "وكانت ظلال الأعمدة تمتد كأصابع عملاقة على الحجر",
                "english": (
                    "And the shadows of the columns stretched like giant fingers over the stone"
                ),
            },
            {
                "jordanian": "الناس بتشوفها آثار، وإحنا كانت ملعبنا ومدرستنا",
                "msa": "يراها الناس آثاراً، أما نحن فكانت ملعبنا ومدرستنا",
                "english": "People see ruins; for us it was our playground and our school",
            },
        ),
    ),
    StorySeed(
        key="echoes-of-petra",
        title="The Echoes of Petra",
        category="history",
        place="petra",
        latitude=30.3285,
        longitude=35.4444,
        storyteller="abu-mahmoud",
        language="msa",
        duration_ms=_min(12, 45),
        published_days_ago=45,
        curated=True,
        cover="petra-treasury",
        lines=(
            {
                "msa": "نحت الأنباط هذه الواجهة في الصخر الوردي قبل ألفي عام",
                "english": (
                    "The Nabataeans carved this facade into the rose-red rock"
                    " two thousand years ago"
                ),
            },
            {
                "msa": "وكانوا سادة الماء في قلب الصحراء",
                "english": "They were masters of water in the heart of the desert",
            },
            {
                "msa": "وما زالت قنواتهم تجري على جانبي السيق",
                "english": "Their channels still run along both sides of the Siq",
            },
            {
                "msa": "كان أبي دليلاً هنا، وأنا اليوم دليل مثله",
                "english": "My father was a guide here, and today I am a guide like him",
            },
        ),
    ),
    StorySeed(
        key="spice-market-tales",
        title="Tales from the Spice Market",
        category="folklore",
        place="amman",
        latitude=31.9539,
        longitude=35.9106,
        storyteller="sitti-fatima",
        language="jordanian",
        duration_ms=_min(8, 20),
        published_days_ago=10,
        curated=False,
        cover="spice-market",
        lines=(
            {
                "jordanian": "الزعتر الطيب بدو شمس وصبر",
                "msa": "الزعتر الجيد يحتاج إلى شمس وصبر",
                "english": "Good za'atar needs sun and patience",
            },
            {
                "jordanian": "إمي كانت تحمّص السمسم على نار هادية",
                "msa": "كانت أمي تحمّص السمسم على نار هادئة",
                "english": "My mother toasted the sesame over a low fire",
            },
            {
                "jordanian": "والسماق كانت تجيبه من الجبل كل خريف",
                "msa": "وكانت تجلب السماق من الجبل كل خريف",
                "english": "And she brought the sumac down from the mountain every autumn",
            },
            {
                "jordanian": "الخلطة سر، بس رح أحكيلكم نصه",
                "msa": "الخلطة سر، لكنني سأخبركم بنصفه",
                "english": "The blend is a secret, but I will tell you half of it",
            },
        ),
    ),
    StorySeed(
        key="ceramic-legacy",
        title="The Ceramic Legacy",
        category="personal",
        place="jerash",
        latitude=32.2745,
        longitude=35.8912,
        storyteller="sayegh",
        language="english",
        duration_ms=_min(5, 15),
        published_days_ago=2,
        curated=False,
        cover="ceramic-workshop",
        lines=(
            {
                "english": "Our kiln has been burning in Jerash for four generations",
                "msa": "يشتعل فرننا في جرش منذ أربعة أجيال",
            },
            {
                "english": "My great-grandfather built it from river clay and old Roman bricks",
                "msa": "بناه جدّ أبي من طين النهر ومن طوب روماني قديم",
            },
            {
                "english": "Every pot we make still carries his thumbprint pattern on the base",
                "msa": "وما زالت كل جرّة نصنعها تحمل نقش بصمته على قاعدتها",
            },
            {
                "english": "When my daughter fired her first bowl, the whole family came to watch",
                "msa": "عندما شوت ابنتي أول وعاء لها، جاءت العائلة كلها لتشاهد",
            },
        ),
    ),
)
