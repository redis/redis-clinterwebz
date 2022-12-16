resource "aws_instance" "clinterwebz-ec2" {
    instance_type = "t3.large"
    ami = "ami-09db26f1ef0a9f406"
    vpc_security_group_ids = [aws_security_group.inbound.id]
    subnet_id = aws_subnet.public-1a.id
    associate_public_ip_address = true
    key_name = aws_key_pair.public_key.key_name

    tags = {
        Name = "clinterwebz"
    }
}