# Activation and experimental AI generation

Real AI generation has **not** been demonstrated by this project. Installing the optional runtime does not establish that the licensed pipeline works.

The initial helper had an activation stability defect, diagnosed on 2026-10-12: the bundled Python runtime's first UUID node getter supplied a synthetic multicast address even though later getters could find the real NIC. Fresh processes therefore generated changing or empty fingerprints. The original core accepted some of these synthetic addresses. The helper now selects a verified permanent physical NIC from Linux sysfs, saves its selector privately, and verifies the same real address on each startup before populating Python's UUID node cache. Commercial core files, fingerprint hashing and signature verification remain unchanged.

If your request code changed on every launch before this fix, an issued licence may be bound to a synthetic identifier. Do not alter that licence or impersonate the old hash. Update the helper, confirm a stable code across restarts, and ask Shapecast to reissue against the corrected request. The saved selector contains only a local interface name and its hashed identifier, never a licence key. Neither this file nor request codes belong in source control.

## Why the Linux request code is shorter

The original core collects up to three fingerprint fields: a hardware identifier, a system identifier and the MAC address. The first two use Windows registry values or macOS platform identifiers; those lookups return no value on native Linux. The resulting request therefore contains the product/version information and the hash of one real MAC address. It is shorter because two identifier fields are absent.

That shorter payload is separate from the changing-code defect in the bundled Python runtime. The stable-adapter workaround fixes the changing MAC input without inventing the missing Windows/macOS identifiers. The original local machine matcher accepts a single shared identifier when it matches; vendor issuance and successful activation with this Linux request still need verification.

On 2026-10-12, the maintainer reported the same corrected request code produced by the verified physical adapter. A licence had been received for an earlier unstable request; activation using the corrected identity has not been established. Actual request codes, licence contents and support correspondence are kept out of this repository.

The normal native profile preserves the original licence verification. Obtain your licence from Shapecast and use the Linux setup page's licence controls. The [vendor activation page](https://shapecast.io/pages/software-activation) is available if online activation fails. Installation and diagnostics do not send order information or activation requests.

The automatic activation hostname could not be resolved during the initial Linux investigation on 2026-10-10. That observation is not proof of a Linux-specific problem and might change. Use the vendor's manual process or contact their support when needed. Do not upload your licence, order number, activation code or launch token to a GitHub issue.

## Optional runtime

For owners who want to investigate licensed generation, this command configures the tested native `trellis.cpp` CLI build in the **native** profile:

```bash
./shapecast-linux runtime --models-dir "$HOME/Models/shapecast"
./shapecast-linux launch --mode native
```

It downloads the checksum-verified CUDA Linux x64 release recorded in `components.lock.json`. It does not download model weights, alter licence verification or change the preview profile. A working NVIDIA driver, compatible models and a valid product licence are still required. The runtime has been checked for CLI availability and GPU detection on the original test machine; inference has not been tested.

Use model files and instructions supplied by Shapecast for your product version. Check the setup page's missing-model list. A populated directory alone does not verify that its models are compatible. Do not interpret an `engine_ready` status as a completed generation test.

The next compatibility milestone is one licensed job using genuine model weights, followed by independent checks of its output and exports. Until then, treat AI generation, text/image generation, rigging and animation as unverified.
