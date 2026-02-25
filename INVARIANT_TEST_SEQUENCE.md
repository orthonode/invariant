# INVARIANT Subnet Test Sequence

## Prerequisites
- Local subtensor node running
- Wallets funded and registered

## Test Commands

### Terminal 1 - Start Miner
```bash
source venv/bin/activate
python miner.py --wallet.name miner1 --wallet.hotkey default --netuid 1
```

### Terminal 2 - Start Validator
```bash
source venv/bin/activate
python validator.py --wallet.name validator1 --wallet.hotkey default --netuid 1
```

## Complete Setup Sequence

### Step 1: Start Subtensor Node
```bash
cd /home/arhant/Development/Bittensor/subtensor
./scripts/localnet.sh
```

### Step 2: Register Subnet and Fund Wallets
```bash
source venv/bin/activate
python instant_register.py
```

### Step 3: Start Miner (Terminal 1)
```bash
source venv/bin/activate
python miner.py --wallet.name miner1 --wallet.hotkey default --netuid 1
```

### Step 4: Start Validator (Terminal 2)
```bash
source venv/bin/activate
python validator.py --wallet.name validator1 --wallet.hotkey default --netuid 1
```

## Notes
- The miner may show "Custom Error 10" warnings but should continue running
- Both processes should remain active and ready to handle tasks
- Default subtensor endpoint is ws://127.0.0.1:9944 (no need to specify)
- Default netuid is 1 for INVARIANT subnet
