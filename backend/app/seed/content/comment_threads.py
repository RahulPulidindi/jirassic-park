"""Filler comment threads.

Mapped by index: a small library of realistic short threads that the seed
builder can apply to filler issues, picked deterministically by issue number.
"""

from __future__ import annotations


THREADS = [
    [
        ("user_chloe_miller", "Repros for me too on the latest TestFlight build."),
        ("user_priya_iyer", "Looking into it - I think it's the same root cause as the previous regression."),
        ("user_chloe_miller", "Thanks!"),
    ],
    [
        ("user_jordan_smith", "I can pick this up after the current sprint if no one else has bandwidth."),
        ("user_sarah_kim", "Sounds good, let's plan it into Sprint 24."),
    ],
    [
        ("user_grace_okafor", "Is this still happening after the rollback? I don't see the alert firing anymore."),
        ("user_raj_patel", "Confirmed clean for the last 24 hours. Closing as fixed by the rollback."),
    ],
    [
        ("user_kenji_ito", "I noticed this too. Should we add a regression test?"),
        ("user_lina_garcia", "Yes - good catch. Added one in the linked PR."),
    ],
    [
        ("user_devon_lee", "Customer also reports this. Bumping priority."),
    ],
    [
        ("user_emma_rossi", "Linked the related dependency upgrade. They should be done together."),
        ("user_owen_walsh", "Agreed, will sequence them."),
    ],
    [
        ("user_marcus_obrien", "Took a stab at this - blocked on a missing IAM permission. Pinging infra."),
        ("user_raj_patel", "Permission granted, unblock yourself."),
        ("user_marcus_obrien", "Working again, PR up."),
    ],
    [
        ("user_amara_singh", "How urgent is this from a customer perspective?"),
        ("user_devon_lee", "Three customers reported in the last week. Not urgent but trending up."),
    ],
    [
        ("user_aki_yamada", "I can probably squeeze this in this sprint if it's small."),
        ("user_raj_patel", "Smaller than it looks once you ignore the legacy adapter."),
        ("user_aki_yamada", "Taken."),
    ],
    [
        ("user_camille_durand", "Design check needed before I land this - mocks?"),
        ("user_sarah_kim", "I'll get a design review on the linked Figma."),
    ],
]
