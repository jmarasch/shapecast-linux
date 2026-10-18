# Review alternate views before geometry

The native Linux interface pauses after alternate-view generation and before queuing any geometry work. The review opens automatically and shows the selected front reference alongside each generated alternate view.

1. Compare the angles. Click an image to enlarge it.
2. Choose **Approve view** for each acceptable alternate view.
3. Choose **Reject & regenerate** to replace only that angle. A new seed and output path prevent reuse of the rejected image. The selected front and other views stay unchanged.
4. Approve the replacement when it is ready.
5. Choose **Continue to geometry** after every alternate view is approved.

**Review later** closes the panel without continuing the cast. Use the review notice to reopen it. Approvals are stored in the cast's database and survive a page refresh or application restart. Waiting for approval does not keep the image model loaded on the GPU. Cancel cast stops the cast using the original cancellation mechanism.

If a browser fails to load a thumbnail, choose **Refresh images**. This reloads the previews without changing the images or their approvals. Approval controls remain disabled for a view until its preview loads.

This step appears only when the cast has alternate images. If automatic side-view selection skips them, choose **Side views: Always** when appropriate for the subject. Front-only casts retain their normal workflow. The front reference is the anchor for regenerated angles; this panel does not regenerate the front or change the image model.

Regeneration runs through Shapecast's existing work queue and original image host. Native regeneration and continuation retain the original vendor licence checks. Failed or interrupted replacement attempts keep the previous image and return the cast to review; a replacement still needs approval. Stale revisions and repeated continuation requests cannot queue geometry twice. The approved replacement images are also used by later texture and export stages.

The helper adds process-local hooks and browser controls; original vendor core and interface files remain unmodified. Image review requests use the authenticated UI origin and a fixed loopback-only relay. No files are uploaded to an external service.

Validation on the development machine used the purchased 0.3.17 core with a separate database and disposable image-stage outputs to check pausing, per-view replacement, stale requests, failed and interrupted regeneration, cancellation, restart recovery and exactly-once geometry dispatch. Browser interaction checked individual approvals, regeneration, thumbnail refresh and explicit continuation. A separate real FLUX image-host test passed the normal vendor generation guard and generated one 1024×1024 back view without changing the front reference. This is not a new end-to-end mesh benchmark or validation on other machines.
