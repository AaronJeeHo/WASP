
import argparse
import sys

import pysam



def parse_options():
    parser = argparse.ArgumentParser(description="This program checks "
                                     "whether reads that overlap SNPs map "
                                     "back to the same location as the "
                                     "original reads after their alleles "
                                     "are flipped by the "
                                     "find_intersecting_snps.py script. "
                                     "Reads where one or more allelic versions "
                                     "map to a different location (or fail "
                                     "to map) are discarded. Reads that are "
                                     "kept are written to the specified "
                                     "keep_bam output file. Reads in the "
                                     "input remap_bam file are expected to "
                                     "have read names encoding the original "
                                     "map location and number of allelic "
                                     "variants. Specifically, the read names "
                                     "should be delimited with the '.' "
                                     "character and "
                                     "contain the following fields: "
                                     "<orig_name>.<coordinate>."
                                     "<read_number>.<total_read_number>. "
                                     "These read names are "
                                     "generated by the "
                                     "find_intersecting_snps.py script.")
    
    parser.add_argument("to_remap_bam", help="input BAM file containing "
                        "original set of reads that needed to "
                        "be remapped after having their alleles flipped."
                        " This file is output by the find_intersecting_snps.py "
                        "script.")
    parser.add_argument("remap_bam", help="input BAM file containing "
                        "remapped reads (with flipped alleles)")
    parser.add_argument("keep_bam", help="output BAM file to write "
                        "filtered set of reads to")

    return parser.parse_args()




def filter_reads(remap_bam):
    # dictionary to keep track of how many times a given read is observed
    read_counts = {}

    # names of reads that should be kept
    keep_reads = set([])
    bad_reads = set([])
    
    for read in remap_bam:
        if read.is_secondary:
            # only keep primary alignments and discard 'secondary' alignments
            continue
        
        # parse name of read, which should contain:
        # 1 - the original name of the read
        # 2 - the coordinate that it should map to
        # 3 - the number of the read
        # 4 - the total number of reads being remapped
        words = read.qname.split(".")
        if len(words) < 4:
            raise ValueError("expected read names to be formatted "
                             "like <orig_name>.<coordinate>."
                             "<read_number>.<total_read_number> but got "
                             "%s" % read.qname)

        # token separator '.' can potentially occur in
        # original read name, so if more than 4 tokens,
        # assume first tokens make up original read name
        orig_name = ".".join(words[0:len(words)-3])
        coord_str, num_str, total_str = words[len(words)-3:]
        num = int(num_str)
        total = int(total_str)

        correct_map = False
        
        if '-' in coord_str:
            # paired end read, coordinate gives expected positions for each end
            c1, c2 = coord_str.split("-")

            if not read.is_paired:
                bad_reads.add(orig_name)
                continue
            if not read.is_proper_pair:
                bad_reads.add(orig_name)
                continue
            
            pos1 = int(c1)
            pos2 = int(c2)
            if pos1 < pos2:
                left_pos = pos1
                right_pos = pos2
            else:
                left_pos = pos2
                right_pos = pos1
                
            # only use left end of reads, but check that right end is in
            # correct location
            if read.pos < read.next_reference_start or (read.pos == read.next_reference_start and read.is_read1 and not read.is_read2):
                if pos1 == read.pos+1 and pos2 == read.next_reference_start+1:
                    # both reads mapped to correct location
                    correct_map = True
            else:
                # this is right end of read
                continue   
        else:
            # single end read
            pos = int(coord_str)

            if pos == read.pos+1:
                # read maps to correct location
                correct_map = True

        if correct_map:
            if orig_name in read_counts:
                read_counts[orig_name] += 1
            else:
                read_counts[orig_name] = 1

            if read_counts[orig_name] == total:
                # all alternative versions of this read
                # mapped to correct location
                if orig_name in keep_reads:
                    raise ValueError("saw read %s more times than "
                                     "expected in input file" % orig_name)
                keep_reads.add(orig_name)

                # remove read from counts to save mem
                del read_counts[orig_name]
        else:
            # read maps to different location
            bad_reads.add(orig_name)

    return keep_reads, bad_reads
    



def write_reads(to_remap_bam, keep_bam, keep_reads, bad_reads):

    keep_count = 0
    bad_count = 0
    discard_count = 0

    for read in to_remap_bam:
        if read.qname in bad_reads:
            bad_count += 1
        elif read.qname in keep_reads:
            keep_count += 1
            keep_bam.write(read)
        else:
            discard_count += 1

    sys.stderr.write("keep_reads: %d\n" % keep_count)
    sys.stderr.write("bad_reads: %d\n" % bad_count)
    sys.stderr.write("discard_reads: %d\n" % discard_count)
    

    
def main(to_remap_bam_path, remap_bam_path, keep_bam_path):
    to_remap_bam = pysam.Samfile(to_remap_bam_path)
    remap_bam = pysam.Samfile(remap_bam_path)
    keep_bam = pysam.Samfile(keep_bam_path, "wb", template=to_remap_bam)

    keep_reads, bad_reads = filter_reads(remap_bam)
    
    write_reads(to_remap_bam, keep_bam, keep_reads, bad_reads)
        


if __name__ == "__main__":
    options = parse_options()
    main(options.to_remap_bam, options.remap_bam, options.keep_bam)

