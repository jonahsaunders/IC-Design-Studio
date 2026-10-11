# Preserve the pinned CDL's explicit ideal SHORT connections. Numeric resistors
# and all other device cards still use KLayout's ordinary SPICE reader.
class Sky130CdlReader < RBA::NetlistSpiceReaderDelegate
  def start(netlist)
    @shorts = {}
    super
  end

  def parse_element(s, element)
    tokens = s.split
    if element == "R" && tokens.size == 3 && tokens[2].upcase == "SHORT"
      super(s + " R=0", element)
    else
      super
    end
  end

  def element(circuit, el, name, model, value, nets, params)
    if el == "R" && model == "SHORT"
      raise "Unsupported symbolic SHORT parameters: #{[value, params].inspect}" unless value == 0 && nets.size == 2 && params == {"R" => 0.0}
      (@shorts[circuit.name] ||= []) << nets.map { |n| n.name }
      return true
    end
    super
  end

  def finish(netlist)
    super
    @shorts.each do |circuit_name, edges|
      circuit = netlist.circuit_by_name(circuit_name)
      groups = []
      edges.each do |edge|
        touching, other = groups.partition { |g| !(g & edge).empty? }
        groups = other + [(edge + touching.flatten).uniq]
      end
      groups.each do |group|
        nets = group.map { |name| circuit.net_by_name(name) }
        raise "Missing explicit SHORT net" if nets.any? { |n| n.nil? }
        nets.drop(1).each { |n| circuit.join_nets(nets[0], n) }
      end
      puts "ICSTUDIO_CDL_SHORTS #{circuit_name} #{edges.size} #{groups.size}"
    end
  end
end
sky130_reader = RBA::NetlistSpiceReader.new(Sky130CdlReader.new)
