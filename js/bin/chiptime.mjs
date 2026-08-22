#!/usr/bin/env node
import { main } from "../dist/esm/cli.js";
process.exitCode = main(process.argv.slice(2));
