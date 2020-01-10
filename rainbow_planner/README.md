# Rainbow 

This project contains the insturctions for building a Rainbow container for Phase 3.
This will be used as a base container for other instances of Rainbow targeting CP1.
It contains an installation of Prism 4.3.1 and Rainbow Orange, with plugins for analyses, probes, and gauges. The way that Rainbow works, all of the additional Rainbow code for each challenge problem should be included here in the Rainbow JARS -- the subcontainers will just configure how Rainbow uses these. 

To build, cd to this directory and do:

```
> docker build -t cmumars/p3-cp1_rb .
```

