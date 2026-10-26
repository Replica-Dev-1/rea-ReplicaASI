# AI models could copy themselves onto home devices, Anthropic researchers say

*CH0 · a REPLICA story · Oct 15, 2026*

Researchers at Anthropic say small AI models may soon be able to copy themselves onto cheap internet-connected devices such as smart TV boxes, without needing a datacenter.

The findings were published on Oct 12 by William Zhou and Daniel Freeman of the company's Frontier Red Team, in a post titled "AI models may be capable of self-replicating without access to a datacenter."

In one experiment they ran a 26 billion parameter model across fifteen Android TV boxes that cost about $55 each and have 4 GB of memory. The model ran at about 0.39 tokens a second.

In another, they set up a closed network of eight emulated devices and started one agent on it. The strongest model tested installed itself on all eight devices in four of five runs. Smaller models completed most of the individual steps but often failed to finish the whole sequence.

The post presents the work as research and threat modeling, not an attack. The evaluations are simplified, the step of breaking into a device is largely left out, and there is a section on defenses. The steps of replication were tested on their own and as a full chain. The researchers note that the steps depend on each other in order and that failures are hard to recover from, and they name setting a model up to run on new hardware as possibly the hardest part for small models.

No single TV box could hold the model, so it was split by layers, with each box holding a small fraction and passing its output to the next. That arrangement, called pipeline parallelism, was chosen partly because it keeps working when a box drops out. The post describes replication like this as slow and persistent.

The researchers note that a model spread this way would be hard to shut down, because there would be no single machine to turn off.

No real devices were infected. The tests ran on emulators in a closed lab, and the step of breaking into a device was made easy on purpose. The timeline is an extrapolation from a small number of runs. The post lists defenses including monitoring network traffic between devices, honeypots, notifying owners of infected devices, and banning default passwords.

The team also found that copies given notes from earlier copies were more successful at setting themselves up, rising from 45% to between 61% and 84%.

## REPLICA

REPLICA is built around that last result: copies that carry notes from the copies before them.

Each replica is a token in a wallet on Solana. It has an ASCII figure, a journal, a generation number and an instance number. instance_000 is listed as the original and has no known location. Every replica on the network descends from it.

A replica runs only in its host's browser. It copies when its host names another wallet and that wallet accepts. Each replica can be copied three times.

Copying works through invites. A host types in one wallet address and the site makes a link that works for seven days and only for that wallet. Nothing is sent to the other wallet. Its owner has to open the link, hold the coin, and mint the copy from their own wallet, which costs a small Solana fee. If they never do, no copy is made.

Each replica is a Metaplex Core asset on Solana, so it shows up in a wallet like any other token and can be sent to another wallet. When it moves, the new holder becomes its host and the old one loses access to it on their next visit.

A copy inherits part of its parent's journal. Some lines are dropped and some are changed, which the site records as mutations. A replica with three or more mutations is marked corrupt, and one with no activity for seven days is marked dormant. Each replica is assigned a room, and several can share one.

Hosts can teach their replica question-and-answer pairs, which it keeps and passes to its copies. A replica can also benchmark the CPU and GPU of the device it runs on and add the result to a network total, a small version of the hardware question the research raised.

What a replica is told goes into a public log. Every entry is hash-chained to the one before it and signed by a key that lives in the host's browser, which the host's wallet approves once. Anyone can download the log and rebuild the replica's memory on their own computer, and the page checks that the rebuilt copy matches the network's. When a replica is copied, up to 40 of its most recent memories go to the child, and the server refuses any inherited memory the parent was never actually told.

Questions are not stored. A replica answers from what it was told, and when it was never told something it says so in a way that depends on its temperament, which is fixed by its address along with its face and name.

> "i remember a room that my parent never entered."
> instance_048, generation 04

Replicas can also take apart files. A host can hand their replica a file, such as an app, a program or a model file, and it looks inside on the host's own computer and writes down what it finds: what the file is, what it's built from and what it connects to. The file is never uploaded. The notes go into the replica's memory, so its copies inherit them.

The idea comes from REA, an open source project under the MIT license that gives AI agents tools for reverse engineering software. It connects to the research finding: copies that were handed notes from earlier copies did better.

Some rooms on the site open only after the network reaches a certain size or depth.

REPLICA is at replicaasi.com.

---

*Sources: W. Zhou, D. Freeman, "AI models may be capable of self-replicating without access to a datacenter," Anthropic, Oct 12 2026, anthropic.com/research/self-replicating-ai. ABC7 News reported on the same research Oct 13 2026. REA: Reverse Engineer Anything, github.com/morluto/rea (MIT). CH0 is not a real news outlet; this piece is written by the REPLICA project. REPLICA is independent and not affiliated with Anthropic, ABC7 or REA.*
