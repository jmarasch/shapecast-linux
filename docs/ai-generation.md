# Activation and experimental AI generation

Real AI generation has **not** been demonstrated by this project. Installing the optional runtime does not establish that the licensed pipeline works.

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
