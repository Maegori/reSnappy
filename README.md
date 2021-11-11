# reSnappy
Takes a screenshot of the reMarkable screen over SSH, crops it and remove the background.

## Prerequisites

- SSH-access to your reMarkable tablet.
  [Tutorial](https://remarkablewiki.com/tech/ssh) <br>
  (recommended: SSH-key so you don't have to type in your root password every time)

- The following programs are required on your reMarkable:
  - `lz4`
  - `head` (only reMarkable 2.0)