import asyncio
import database
import json

async def run_tests():
    await database.init_db()

    # insert pokemon
    costumes_json = json.dumps([
        {"name": "JAN_2020", "image_url": "url", "shiny_image_url": "url"}
    ])

    sid = await database.upsert_pokemon_species(
        pokedex_num=1,
        name='Bulbasaur',
        form='Normal',
        type1='Grass',
        costumes=costumes_json
    )

    # insert users
    await database.add_user_account(1001, '1111', 'Red', 'EU', is_main=True)
    await database.add_user_account(1002, '2222', 'Blue', 'EU', is_main=True)
    u1_account = await database.get_user_accounts(1001)
    u2_account = await database.get_user_accounts(1002)

    # listing A (wants JAN_2020)
    aid = await database.add_listing(1001, u1_account[0]['id'], 'WANT', sid, costume='JAN_2020')

    # candidate B (has none)
    bid1 = await database.add_listing(1002, u2_account[0]['id'], 'HAVE', sid)

    # match WANT JAN_2020 against HAVE None
    res1 = await database.find_candidates('HAVE', sid, False, False, False, False, False, False, False, 'JAN_2020', 1001)
    print("Match against none:", len(res1))

    # candidate C (has FALL_2019)
    bid2 = await database.add_listing(1002, u2_account[0]['id'], 'HAVE', sid, costume='FALL_2019')
    res2 = await database.find_candidates('HAVE', sid, False, False, False, False, False, False, False, 'JAN_2020', 1001)
    print("Match against none and fall:", len(res2))

    for r in res2:
        print("Matched:", r['costume'])


asyncio.run(run_tests())
