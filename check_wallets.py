from wallet_finder import analyze_wallet

wallets = [
    "HGLsFsHy9NxuYWJe88Lyyrxvw95rDkHfPvid3AUPMbpj",
    "2ZmG87ddU7rcusmzgqRMu91FSrCb5jTnpGrD9yUevbr6",
    "3PQy4TP4EaANumR8tyi9C8DPkGj9YPZ5cgF4fJyY8yBH",
    "G3tdM1ZNS8jsViGBNXfMsXyvwJunSsg8ghsmzc8XgUnW",
    "5U9HR344Nb6oGzFpLePBMkU1GS8BCUUh2PCE2vhUgEFb",
    "7kJjCzUcVcVU4drt1Zv7oNSdUHCtDj2YTQLkR2hshDkw",
    "2TXzbo7jYowkYLZBxT8g5Qowp5umrqGS7jS69c2Sm84a",
    "GmRC6EhKtBEcKM1bjCBzamWDy3qmP5z2Kc9tYjQuc2Pn",
    "AmihGf3CGJNgjJBkb79Y9u9GRima4CeKVtUtJiMoVJjp",
    "784bxySScJMfKMbFte4nJnb5XErR1FibNJLK7Jpqiyy4",
    "31AN7NRmDgGYj31nHza7j9VyVgyP8SkrnSABwBtXvPTC",
    "Hp9dZSwrk87fspfB7qpWsZVHpCBdtVksRdRTkGsuAojC",
    "BMi4kPUNgNFnnXuL1HB7tPGZ5v5CzNJZqZm5nFe74ayh",
    "3KE2VpqdM3Ac3U2zMJAK3MMfDdQN8mKrhKY71ichegKM",
    "GB7ryLgbytA37cfF6ACoDyigcJUQfDb4RFHktMtsqQNg",
    "93JH3k5ckFP4AxRgHbNt3YfKVS2QdYCwcKcqTqzENfck",
    "F72rukmZ7rap4i7A7htiE1ZjYRiXLexVgs94XwqHjpTa",
    "BPDYjwyuxtZExAeAdUZmQ9s21L7NAB8V2zX2neeZLmce",
    "D5qq1C9EvAjAD4WzX7EMFH4TddJFZ6MxFB6KfC8wW7W6",
    "H1QERpW1VaP9FvMeSJj9ELCeKyUQfDEEchYLRKEHLi9u"
]

for w in wallets:
    print(f"\n→ {w[:8]}...")
    result, reason = analyze_wallet(w)
    if result:
        print(f"  ✅ APROBADA | SOL: {result['sol_balance']} | TXs: {result['tx_count']} | Edad: {result['age_days']}d | Tokens: {result['unique_tokens']}")
    else:
        print(f"  ❌ {reason}")