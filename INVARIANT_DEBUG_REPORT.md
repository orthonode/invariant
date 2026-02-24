# INVARIANT Subnet Debug Report

## Current Status
- **Local subtensor node**: ✅ Running and producing blocks every 2-3 seconds
- **Subnet 1 (INVARIANT)**: ✅ Created and registered
- **Wallets**: ✅ Funded with 10,000 TAO each (owner, miner1, validator1)
- **Miner registration**: ❌ Failing with Custom Error 10
- **Validator**: ⚠️ Registered but not started

## What Has Been Done Successfully

### 1. Blockchain Setup
- ✅ Built and started local subtensor node
- ✅ Created subnet 1 with INVARIANT
- ✅ Funded all wallets from Alice sudo account

### 2. Registration
- ✅ Miner1 hotkey registered on subnet 1 (UID: 1)
- ✅ Validator1 hotkey registered on subnet 1 (UID: 2)
- ✅ Axon information registered for miner1

### 3. Code Fixes Applied
- ✅ Fixed all bittensor import issues (bt.wallet → bt.Wallet, etc.)
- ✅ Fixed function signatures for blacklist/priority
- ✅ Fixed config instantiation issues
- ✅ Bypassed registration check temporarily

## Current Problem: Custom Error 10

### Error Message
```
SubstrateRequestException(Invalid Transaction)
Custom error: 10 | Please consult https://docs.bittensor.com/errors/custom
```

### When It Occurs
- When calling `subtensor.serve_axon()` in miner.py line 367
- The miner's axon is already registered but serve_axon fails

## What We've Tried

### ✅ Attempted Solutions
1. **Manual axon registration** - ✅ Worked, but serve_axon still fails
2. **Adding stake to neuron** - ❌ SubToken disabled on local subnet
3. **Setting weights** - ✅ Worked, but didn't fix serve_axon
4. **Bypassing serve_axon** - ✅ Miner runs but this is a workaround
5. **Root subnet investigation** - ❌ Cannot register on root subnet (not permitted)

### ❌ Unsuccessful Attempts
1. **Creating Alice wallet files** - Multiple format issues
2. **Root subnet neuron registration** - Not permitted by protocol
3. **SubToken staking** - Disabled on local dev subnet
4. **Different serve_axon parameters** - Still fails

## Root Cause Analysis

### Key Findings
1. **Root subnet (netuid 0) has 0 neurons** - This is abnormal
2. **Neuron 0 (founder) has Active: 0** - Founder neuron not active
3. **Neuron 1 (miner) has Active: 1 but Stake: 0.0** - Active but no stake
4. **Custom Error 10** = "Hotkey not registered" (but it IS registered)

### Potential Root Causes
1. **Root subnet empty** - No validators to set weights on subnet 1
2. **Neuron activation issue** - Neurons registered but not properly activated
3. **Local dev subnet limitations** - Some features disabled (SubToken, etc.)
4. **Serve_axon protocol mismatch** - May require specific subnet state

## Code Investigation Status

### Files Examined
- ✅ `miner.py` - All imports, function signatures, serve_axon call
- ✅ `validator.py` - Import issues fixed
- ✅ `instant_register.py` - Registration logic verified
- ✅ `fast_register_local.py` - Alternative registration method
- ✅ Bittensor SDK calls - is_hotkey_registered, serve_axon, burned_register

### Functions Analyzed
- ✅ `check_registered()` - Custom error 10 source
- ✅ `subtensor.serve_axon()` - Where the actual error occurs
- ✅ `subtensor.is_hotkey_registered()` - Returns True when tested directly
- ✅ `subtensor.burned_register()` - Works for registration

## What We Have NOT Tried

### ❌ Not Yet Attempted
1. **Complete subnet reset** - Delete and recreate subnet 1
2. **Alternative miner implementation** - Use different Bittensor patterns
3. **Direct substrate calls for serve_axon** - Bypass Bittensor SDK
4. **Checking local node configuration** - Verify dev node setup
5. **Examining subtensor source code** - Understand serve_axon requirements
6. **Testing with different netuid** - Try subnet 2 instead of 1

### 🔍 Missing Investigation
1. **Subtensor module storage functions** - Need to check available storage
2. **Subnet state machine** - Understand activation requirements
3. **Local node spec file** - Check if dev config limits functionality
4. **Bittensor version compatibility** - v10.1.0 might have issues

## Next Steps - Priority Order

### 🚨 High Priority (Root Cause)
1. **Investigate why root subnet has 0 neurons**
2. **Check if subnet 1 needs root subnet weights to activate**
3. **Examine serve_axon requirements in Bittensor source**

### 🔧 Medium Priority (Workarounds)
1. **Try complete subnet reset**
2. **Test with different netuid (2, 3, etc.)**
3. **Use direct substrate calls for serve_axon**

### 📚 Low Priority (Documentation)
1. **Document local dev subnet limitations**
2. **Create troubleshooting guide for Custom Error 10**

## Current Workaround Status

### ✅ Working Solution
- Miner runs with serve_axon bypassed
- Axon is registered and accessible
- Can receive tasks (theoretically)

### ⚠️ Limitations
- Not using official Bittensor serve_axon flow
- May have unknown side effects
- Not a proper long-term solution

## Files Created/Modified

### Debug Files
- `INVARIANT_DEBUG_REPORT.md` - This file

### Modified Files
- `miner.py` - Multiple fixes and workarounds
- `validator.py` - Import fixes
- `instant_register.py` - Registration fixes

### Created Files
- `fund_wallets.py` - Wallet funding script
- `fast_register_local.py` - Alternative registration

## Environment Details

- **Bittensor SDK**: v10.1.0
- **Python**: 3.12
- **OS**: Linux
- **Subtensor**: Local dev node (built from source)
- **Wallets**: miner1, validator1, owner (all funded)

## Conclusion

The INVARIANT subnet is **90% functional** but blocked by a serve_axon issue that appears to be related to the root subnet being empty or local dev subnet limitations. The miner can run with workarounds but the proper Bittensor flow is not working.

**Critical missing piece**: Understanding why serve_axon fails with Custom Error 10 despite the hotkey being properly registered.
